from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv

from .chunker import Chunk
from .hybrid_retriever import RetrievalResult
from .retriever import requested_figure_numbers


DEFAULT_MODEL = "deepseek-v4-flash"
DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MAX_EVIDENCE = 10
DEFAULT_MAX_CONTEXT_CHARS = 14_000


SYSTEM_PROMPT = """You are a careful academic-paper question answering assistant.

Answer only from the supplied evidence excerpts. Do not use outside knowledge as
if it came from the paper.

Rules:
1. Directly answer the user's question in the user's main language.
2. Cite every important factual claim with one or more evidence IDs, for example
   [E1] or [E1][E3].
3. Use only evidence IDs that appear in the supplied context.
4. Distinguish statements made directly by the paper from your cautious synthesis.
5. Do not invent page numbers, definitions, numerical values, figure details, or
   conclusions.
6. If the evidence cannot support an answer, say exactly:
   当前论文片段中没有足够依据
7. Keep the answer focused. Do not reproduce the evidence excerpts at length.
"""


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    chunk_id: str
    retrieval_rank: int
    chunk: Chunk
    retrieval_score: float
    retrieval_source: str
    bbox: tuple[float, float, float, float] | None = None


@dataclass(frozen=True)
class QAResponse:
    answer: str
    raw_answer: str
    evidence: tuple[Evidence, ...]
    cited_evidence_ids: tuple[str, ...]
    model: str


class QAEngineError(RuntimeError):
    pass


def load_environment() -> None:
    load_dotenv()


def get_api_key() -> str | None:
    load_environment()
    value = os.getenv("DEEPSEEK_API_KEY", "").strip()
    return value or None


def get_model_name() -> str:
    load_environment()
    return os.getenv("DEEPSEEK_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL


def get_base_url() -> str:
    load_environment()
    return os.getenv("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL).strip() or DEFAULT_BASE_URL


def is_llm_available() -> bool:
    return get_api_key() is not None


def make_chunk_id(chunk: Chunk) -> str:
    identity = "\x1f".join(
        [
            chunk.paper_title or "",
            str(chunk.page),
            chunk.chunk_type,
            chunk.figure_id or "",
            chunk.section or "",
            str(chunk.paragraph_id or ""),
            chunk.text,
        ]
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]


SUMMARY_QUERY_RE = re.compile(
    r"(主要内容|主要讲|文章讲|论文讲|总结|概述|核心内容|核心结论|"
    r"main\s+(?:idea|content|contribution)|summary|overview|what\s+is\s+"
    r"(?:this|the)\s+paper\s+about)",
    flags=re.IGNORECASE,
)


def _question_type(question: str) -> str:
    if requested_figure_numbers(question):
        return "figure"
    if SUMMARY_QUERY_RE.search(question):
        return "summary"
    return "general"


def _chunk_type_bonus(chunk_type: str, question_type: str) -> float:
    if question_type == "figure":
        return {
            "caption": 0.14,
            "figure_discussion": 0.13,
            "figure_context": 0.09,
            "body": 0.05,
            "introduction": 0.02,
            "conclusion": 0.02,
        }.get(chunk_type, 0.0)

    if question_type == "summary":
        return {
            "conclusion": 0.14,
            "introduction": 0.12,
            "body": 0.07,
            "figure_discussion": 0.03,
            "figure_context": 0.02,
            "caption": 0.0,
        }.get(chunk_type, 0.0)

    return {
        "body": 0.08,
        "conclusion": 0.06,
        "introduction": 0.05,
        "figure_discussion": 0.05,
        "figure_context": 0.04,
        "caption": 0.01,
    }.get(chunk_type, 0.0)


def _evidence_value(result: RetrievalResult, rank: int, question: str) -> float:
    chunk = result.chunk
    score = result.score + (chunk.quality_score * 0.08)
    score += _chunk_type_bonus(chunk.chunk_type, _question_type(question))
    score += max(0.0, 0.04 - rank * 0.003)
    return score


def select_context(
    results: list[RetrievalResult],
    question: str = "",
    max_evidence: int = DEFAULT_MAX_EVIDENCE,
    max_context_chars: int = DEFAULT_MAX_CONTEXT_CHARS,
) -> list[Evidence]:
    if not results or max_evidence <= 0 or max_context_chars <= 0:
        return []

    ranked = sorted(
        enumerate(results),
        key=lambda item: _evidence_value(item[1], item[0], question),
        reverse=True,
    )

    selected_results: list[tuple[int, RetrievalResult]] = []
    selected_ids: set[str] = set()
    total_chars = 0

    for result_index, result in ranked:
        chunk_id = make_chunk_id(result.chunk)
        if chunk_id in selected_ids:
            continue

        chunk_chars = len(result.chunk.text)
        if selected_results and total_chars + chunk_chars > max_context_chars:
            continue

        selected_results.append((result_index, result))
        selected_ids.add(chunk_id)
        total_chars += chunk_chars
        if len(selected_results) >= max_evidence:
            break

    # Keep the final evidence numbering aligned with retrieval order in the UI.
    selected_results.sort(key=lambda item: item[0])

    return [
        Evidence(
            evidence_id=f"E{index}",
            retrieval_rank=result_index + 1,
            chunk_id=make_chunk_id(result.chunk),
            chunk=result.chunk,
            retrieval_score=result.score,
            retrieval_source=result.source,
        )
        for index, (result_index, result) in enumerate(selected_results, start=1)
    ]


def build_context(evidence: list[Evidence]) -> str:
    blocks: list[str] = []
    for item in evidence:
        chunk = item.chunk
        metadata = [
            f"evidence_id: {item.evidence_id}",
            f"chunk_id: {item.chunk_id}",
            f"retrieval_rank: {item.retrieval_rank}",
            f"page: {chunk.page}",
            f"chunk_type: {chunk.chunk_type}",
        ]
        if chunk.figure_id:
            metadata.append(f"figure_id: {chunk.figure_id}")
        if chunk.section:
            metadata.append(f"section: {chunk.section}")
        if chunk.section_title:
            metadata.append(f"section_title: {chunk.section_title}")

        blocks.append(
            "\n".join(
                [
                    f"[{item.evidence_id}]",
                    *metadata,
                    f"text: {chunk.text}",
                ]
            )
        )
    return "\n\n".join(blocks)


def cited_evidence_ids(answer: str, evidence: list[Evidence]) -> tuple[str, ...]:
    valid_ids = {item.evidence_id for item in evidence}
    found: list[str] = []
    for match in re.finditer(r"\bE(\d+)\b", answer, flags=re.IGNORECASE):
        evidence_id = f"E{int(match.group(1))}"
        if evidence_id in valid_ids and evidence_id not in found:
            found.append(evidence_id)
    return tuple(found)


def render_citations(answer: str, evidence: list[Evidence]) -> str:
    evidence_by_id = {item.evidence_id: item for item in evidence}

    def replace(match: re.Match[str]) -> str:
        evidence_id = f"E{int(match.group(1))}"
        item = evidence_by_id.get(evidence_id)
        if item is None:
            return match.group(0)

        chunk = item.chunk
        label = f"{evidence_id} · Page {chunk.page} · {chunk.chunk_type}"
        if chunk.figure_id:
            label += f" · {chunk.figure_id}"
        return f"[{label}]"

    return re.sub(r"\[E(\d+)\]", replace, answer, flags=re.IGNORECASE)


def _create_client(api_key: str, base_url: str) -> Any:
    try:
        from openai import OpenAI
    except ImportError as error:
        raise QAEngineError(
            "缺少 openai 依赖，请先运行 pip install -r requirements.txt。"
        ) from error

    return OpenAI(api_key=api_key, base_url=base_url, timeout=60.0, max_retries=1)


def generate_answer(
    question: str,
    results: list[RetrievalResult],
    *,
    max_evidence: int = DEFAULT_MAX_EVIDENCE,
    max_context_chars: int = DEFAULT_MAX_CONTEXT_CHARS,
    client: Any | None = None,
) -> QAResponse:
    question = question.strip()
    if not question:
        raise QAEngineError("问题不能为空。")

    evidence = select_context(
        results,
        question=question,
        max_evidence=max_evidence,
        max_context_chars=max_context_chars,
    )
    if not evidence:
        raise QAEngineError("没有可用于生成回答的论文证据。")

    api_key = get_api_key()
    if client is None and api_key is None:
        raise QAEngineError("未配置 DEEPSEEK_API_KEY。")

    model = get_model_name()
    context = build_context(evidence)
    user_prompt = "\n".join(
        [
            f"User question:\n{question}",
            "",
            "Paper evidence:",
            context,
            "",
            "Write the evidence-grounded answer now.",
        ]
    )

    active_client = client or _create_client(api_key or "", get_base_url())
    try:
        response = active_client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            stream=False,
            extra_body={"thinking": {"type": "disabled"}},
        )
    except Exception as error:
        raise QAEngineError(f"DeepSeek API 调用失败：{error}") from error

    raw_answer = (response.choices[0].message.content or "").strip()
    if not raw_answer:
        raise QAEngineError("DeepSeek 返回了空回答。")

    return QAResponse(
        answer=render_citations(raw_answer, evidence),
        raw_answer=raw_answer,
        evidence=tuple(evidence),
        cited_evidence_ids=cited_evidence_ids(raw_answer, evidence),
        model=model,
    )
