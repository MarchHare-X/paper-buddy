from __future__ import annotations

import math
import re
from collections import Counter

from .chunker import Chunk


TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")
CHINESE_FIGURE_RE = re.compile(r"图\s*(?P<number>\d+[A-Za-z]?)")
ENGLISH_FIGURE_RE = re.compile(
    r"(?<![A-Za-z0-9_])fig(?:ure)?\s*\.?\s*(?P<number>\d+[A-Za-z]?)(?![A-Za-z0-9_])",
    re.IGNORECASE,
)
FIGURE_CAPTION_START_RE = re.compile(
    r"^\s*(?:\d+\s+)?(?:[A-Z][A-Za-z]+(?:\s*&\s*[A-Z][A-Za-z]+)?\s+)?"
    r"fig(?:ure)?\.?\s*(?P<number>\d+[A-Za-z]?)\s*[\.:]",
    re.IGNORECASE,
)


def normalize_query(text: str) -> str:
    text = CHINESE_FIGURE_RE.sub(r" figure \g<number> ", text)
    text = re.sub(r"(?i)\b(fig(?:ure)?)\s+\.", r"\1.", text)
    return text


def tokenize(text: str, include_chinese_chars: bool = False) -> list[str]:
    normalized = normalize_query(text)
    tokens = [token.lower() for token in TOKEN_RE.findall(normalized)]
    if include_chinese_chars:
        tokens.extend(re.findall(r"[\u4e00-\u9fff]", normalized))
    return tokens


def requested_figure_numbers(query: str) -> set[str]:
    normalized = normalize_query(query)
    return {match.group("number").lower() for match in ENGLISH_FIGURE_RE.finditer(normalized)}


def chunk_figure_numbers(chunk: Chunk) -> set[str]:
    if not chunk.figure_id:
        return set()
    return requested_figure_numbers(chunk.figure_id)


def text_mentions_figure(text: str, figure_number: str) -> bool:
    normalized = normalize_query(text)
    escaped_number = re.escape(figure_number)
    pattern = re.compile(
        rf"(?<![A-Za-z0-9_])fig(?:ure)?\s*\.?\s*{escaped_number}(?![A-Za-z0-9_])",
        re.IGNORECASE,
    )
    return bool(pattern.search(normalized))


def mentioned_figure_numbers(text: str) -> set[str]:
    normalized = normalize_query(text)
    return {match.group("number").lower() for match in ENGLISH_FIGURE_RE.finditer(normalized)}


def starts_with_other_figure_caption(text: str, figure_numbers: set[str]) -> bool:
    match = FIGURE_CAPTION_START_RE.match(normalize_query(text))
    if match is None:
        return False
    return match.group("number").lower() not in figure_numbers


def substantially_overlaps(text: str, context_texts: list[str]) -> bool:
    normalized = " ".join(text.split()).lower()
    if not normalized:
        return False

    normalized_tokens = set(tokenize(normalized))
    if not normalized_tokens:
        return False

    for context_text in context_texts:
        context = " ".join(context_text.split()).lower()
        if normalized in context or context in normalized:
            return True
        context_tokens = set(tokenize(context))
        if not context_tokens:
            continue
        overlap = len(normalized_tokens & context_tokens) / min(
            len(normalized_tokens),
            len(context_tokens),
        )
        if overlap >= 0.65:
            return True
    return False


def looks_like_method_or_formula_detail(text: str) -> bool:
    lowered = text.lower()
    method_markers = [
        "following function",
        "this function has",
        "fitting function",
        "parametrization",
        "we limit our fits",
    ]
    if any(marker in lowered for marker in method_markers):
        return True

    math_symbols = sum(text.count(symbol) for symbol in ["∝", "≪", "≫", "𝑏", "𝑟", "𝛼", "𝛽", "𝛾"])
    return math_symbols >= 10


def unique_top_k(scored: list[tuple[Chunk, float]], top_k: int) -> list[tuple[Chunk, float]]:
    selected: list[tuple[Chunk, float]] = []

    for chunk, score in scored:
        if chunk.chunk_type == "body" and any(
            selected_chunk.chunk_type == "body" and selected_chunk.page == chunk.page
            for selected_chunk, _ in selected
        ):
            continue

        same_type_texts = [
            selected_chunk.text
            for selected_chunk, _ in selected
            if selected_chunk.chunk_type == chunk.chunk_type
        ]
        if substantially_overlaps(chunk.text, same_type_texts):
            continue
        selected.append((chunk, score))
        if len(selected) >= top_k:
            break

    return selected


def add_global_context_fallback(
    results: list[tuple[Chunk, float]],
    chunks: list[Chunk],
    top_k: int,
) -> list[tuple[Chunk, float]]:
    if len(results) >= top_k:
        return results

    selected = list(results)
    selected_texts = [chunk.text for chunk, _ in selected]
    conclusions = [chunk for chunk in chunks if chunk.chunk_type == "conclusion"]
    introductions = [chunk for chunk in chunks if chunk.chunk_type == "introduction"]
    global_chunks = (
        conclusions[:1]
        + introductions[:1]
        + conclusions[1:]
        + introductions[1:]
    )

    for chunk in global_chunks:
        if substantially_overlaps(chunk.text, selected_texts):
            continue
        score = 1.5 if chunk.chunk_type == "conclusion" else 1.0
        selected.append((chunk, score))
        selected_texts.append(chunk.text)
        if len(selected) >= top_k:
            break

    return selected


def score_keyword_overlap(query_counts: Counter[str], chunk: Chunk) -> float:
    chunk_terms = tokenize(chunk.text)
    if not chunk_terms:
        return 0.0

    chunk_counts = Counter(chunk_terms)
    overlap_score = sum(
        min(query_count, chunk_counts.get(term, 0))
        for term, query_count in query_counts.items()
    )
    if overlap_score == 0:
        return 0.0

    return overlap_score / math.log(len(chunk_terms) + 10)


def retrieve_figure_context(
    figure_numbers: set[str],
    query_counts: Counter[str],
    chunks: list[Chunk],
    top_k: int,
) -> list[tuple[Chunk, float]]:
    caption_pages = {
        chunk.page
        for chunk in chunks
        if chunk.chunk_type == "caption" and chunk_figure_numbers(chunk) & figure_numbers
    }
    if not caption_pages:
        return []

    target_context_texts = [
        chunk.text
        for chunk in chunks
        if chunk.chunk_type == "figure_context" and chunk_figure_numbers(chunk) & figure_numbers
    ]
    target_discussion_texts = [
        chunk.text
        for chunk in chunks
        if chunk.chunk_type == "figure_discussion" and chunk_figure_numbers(chunk) & figure_numbers
    ]
    scored: list[tuple[Chunk, float]] = []

    for chunk in chunks:
        own_figures = chunk_figure_numbers(chunk)

        if chunk.chunk_type == "caption":
            if not (own_figures & figure_numbers):
                continue
            score = 100.0 + score_keyword_overlap(query_counts, chunk)
            scored.append((chunk, score))
            continue

        if chunk.chunk_type == "figure_discussion":
            if not (own_figures & figure_numbers):
                continue
            score = 75.0 + score_keyword_overlap(query_counts, chunk)
            scored.append((chunk, score))
            continue

        if chunk.chunk_type == "figure_context":
            if not (own_figures & figure_numbers):
                continue
            if substantially_overlaps(chunk.text, target_discussion_texts):
                continue
            nearest_caption_page = min(abs(chunk.page - page) for page in caption_pages)
            base_score = 50.0 if nearest_caption_page <= 1 else 35.0
            other_figures = mentioned_figure_numbers(chunk.text) - figure_numbers
            if other_figures:
                base_score -= 6.0
            score = base_score + score_keyword_overlap(query_counts, chunk)
            scored.append((chunk, score))
            continue

        mentions_target = any(text_mentions_figure(chunk.text, number) for number in figure_numbers)
        if starts_with_other_figure_caption(chunk.text, figure_numbers):
            continue

        if substantially_overlaps(chunk.text, target_context_texts):
            continue

        if not mentions_target and looks_like_method_or_formula_detail(chunk.text):
            continue

        other_figures = mentioned_figure_numbers(chunk.text) - figure_numbers
        if other_figures and not mentions_target:
            continue

        nearest_caption_page = min(abs(chunk.page - page) for page in caption_pages)
        is_near_target_figure = nearest_caption_page == 0

        if not mentions_target and not is_near_target_figure:
            continue

        proximity_score = max(0.0, 3.0 - nearest_caption_page)
        mention_score = 3.5 if mentions_target else 0.0
        keyword_score = score_keyword_overlap(query_counts, chunk)
        score = proximity_score + mention_score + keyword_score
        scored.append((chunk, score))

    scored.sort(key=lambda item: item[1], reverse=True)
    results = unique_top_k(scored, top_k)
    return add_global_context_fallback(results, chunks, top_k)


def retrieve(query: str, chunks: list[Chunk], top_k: int = 5) -> list[tuple[Chunk, float]]:
    query_terms = tokenize(query, include_chinese_chars=True)
    if not query_terms:
        return []

    query_counts = Counter(query_terms)
    figure_numbers = requested_figure_numbers(query)

    if figure_numbers:
        figure_results = retrieve_figure_context(figure_numbers, query_counts, chunks, top_k)
        if figure_results:
            return figure_results

    scored: list[tuple[Chunk, float]] = []

    for chunk in chunks:
        keyword_score = score_keyword_overlap(query_counts, chunk)
        if keyword_score == 0:
            continue

        caption_bonus = 1.4 if chunk.chunk_type == "caption" else 1.0
        score = caption_bonus * keyword_score
        scored.append((chunk, score))

    scored.sort(key=lambda item: item[1], reverse=True)
    return unique_top_k(scored, top_k)
