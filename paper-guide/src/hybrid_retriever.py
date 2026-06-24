from __future__ import annotations

from dataclasses import dataclass
from collections import Counter

from .chunker import Chunk
from .retriever import (
    score_keyword_overlap,
    substantially_overlaps,
    tokenize,
)
from .vector_store import search_similar_chunks


@dataclass(frozen=True)
class RetrievalResult:
    chunk: Chunk
    score: float
    source: str
    matched_terms: tuple[str, ...] = ()
    why_selected: str = ""
    vector_score: float | None = None
    keyword_score: float | None = None


def chunk_key(chunk: Chunk) -> tuple[int, str, str, str]:
    normalized_text = " ".join(chunk.text.split()).lower()
    return (
        chunk.page,
        chunk.chunk_type,
        chunk.figure_id or "",
        normalized_text,
    )


def matched_query_terms(query_terms: list[str], chunk: Chunk) -> tuple[str, ...]:
    chunk_terms = set(tokenize(chunk.text))
    seen: list[str] = []
    for term in query_terms:
        if term in chunk_terms and term not in seen:
            seen.append(term)
    return tuple(seen)


def keyword_candidates(
    query: str,
    chunks: list[Chunk],
    candidate_k: int,
) -> list[RetrievalResult]:
    query_terms = tokenize(query, include_chinese_chars=True)
    if not query_terms:
        return []

    query_counts = Counter(query_terms)
    scored: list[RetrievalResult] = []

    for chunk in chunks:
        keyword_score = score_keyword_overlap(query_counts, chunk)
        if keyword_score == 0:
            continue

        matched_terms = matched_query_terms(query_terms, chunk)
        type_bonus = 1.15 if chunk.chunk_type in {"introduction", "conclusion"} else 1.0
        score = keyword_score * type_bonus * max(chunk.quality_score, 0.5)
        scored.append(
            RetrievalResult(
                chunk=chunk,
                score=score,
                source="keyword",
                matched_terms=matched_terms,
                why_selected="keyword term match",
                keyword_score=keyword_score,
            )
        )

    scored.sort(key=lambda result: result.score, reverse=True)
    return scored[:candidate_k]


def merge_candidate(
    existing: RetrievalResult,
    incoming: RetrievalResult,
) -> RetrievalResult:
    sources = set(existing.source.split("+")) | set(incoming.source.split("+"))
    matched_terms = tuple(dict.fromkeys(existing.matched_terms + incoming.matched_terms))
    vector_score = existing.vector_score
    if incoming.vector_score is not None:
        vector_score = max(vector_score or 0.0, incoming.vector_score)
    keyword_score = existing.keyword_score
    if incoming.keyword_score is not None:
        keyword_score = max(keyword_score or 0.0, incoming.keyword_score)

    return RetrievalResult(
        chunk=existing.chunk,
        score=max(existing.score, incoming.score),
        source="+".join(sorted(sources)),
        matched_terms=matched_terms,
        why_selected="; ".join(
            part
            for part in [existing.why_selected, incoming.why_selected]
            if part
        ),
        vector_score=vector_score,
        keyword_score=keyword_score,
    )


def rerank_score(result: RetrievalResult) -> float:
    vector_score = result.vector_score or 0.0
    keyword_score = min((result.keyword_score or 0.0) * 3.0, 1.0)
    quality_score = result.chunk.quality_score
    hybrid_bonus = 0.08 if "keyword" in result.source and "vector" in result.source else 0.0
    direct_evidence_bonus = 0.04 if result.chunk.chunk_type in {"body", "figure_context"} else 0.0
    global_context_bonus = 0.02 if result.chunk.chunk_type in {"introduction", "conclusion"} else 0.0

    return (
        0.58 * vector_score
        + 0.28 * keyword_score
        + 0.10 * quality_score
        + hybrid_bonus
        + direct_evidence_bonus
        + global_context_bonus
    )


def dedupe_results(results: list[RetrievalResult], top_k: int) -> list[RetrievalResult]:
    selected: list[RetrievalResult] = []
    selected_texts: list[str] = []

    for result in results:
        if substantially_overlaps(result.chunk.text, selected_texts):
            continue
        selected.append(result)
        selected_texts.append(result.chunk.text)
        if len(selected) >= top_k:
            break

    return selected


def hybrid_search(
    paper_id: str,
    query: str,
    chunks: list[Chunk],
    top_k: int = 10,
    candidate_k: int | None = None,
) -> list[RetrievalResult]:
    if not chunks:
        return []

    candidate_k = candidate_k or min(len(chunks), max(30, top_k * 4))
    candidate_k = min(candidate_k, len(chunks))

    candidates_by_key: dict[tuple[int, str, str, str], RetrievalResult] = {}

    for vector_result in search_similar_chunks(paper_id, query, top_k=candidate_k):
        result = RetrievalResult(
            chunk=vector_result.chunk,
            score=vector_result.score,
            source="vector",
            why_selected="semantic vector similarity",
            vector_score=vector_result.score,
        )
        candidates_by_key[chunk_key(result.chunk)] = result

    for keyword_result in keyword_candidates(query, chunks, candidate_k=candidate_k):
        key = chunk_key(keyword_result.chunk)
        if key in candidates_by_key:
            candidates_by_key[key] = merge_candidate(candidates_by_key[key], keyword_result)
        else:
            candidates_by_key[key] = keyword_result

    reranked: list[RetrievalResult] = []
    for result in candidates_by_key.values():
        final_score = rerank_score(result)
        why_parts = [result.why_selected]
        if "keyword" in result.source and "vector" in result.source:
            why_parts.append("boosted because both vector and keyword retrieved it")
        if result.chunk.quality_score < 0.8:
            why_parts.append("lower confidence because chunk quality is below 0.80")
        reranked.append(
            RetrievalResult(
                chunk=result.chunk,
                score=final_score,
                source="hybrid" if "+" in result.source else result.source,
                matched_terms=result.matched_terms,
                why_selected="; ".join(part for part in why_parts if part),
                vector_score=result.vector_score,
                keyword_score=result.keyword_score,
            )
        )

    reranked.sort(key=lambda result: result.score, reverse=True)
    return dedupe_results(reranked, top_k=top_k)
