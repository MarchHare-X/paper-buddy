from __future__ import annotations

import re
from dataclasses import dataclass

from .figure_extractor import FigureCaption, parse_caption_start
from .pdf_parser import PageText


@dataclass(frozen=True)
class Chunk:
    text: str
    page: int
    chunk_type: str
    figure_id: str | None = None


def split_text(text: str, chunk_size: int = 900, overlap: int = 120) -> list[str]:
    cleaned = " ".join(text.split())
    if not cleaned:
        return []

    chunks: list[str] = []
    start = 0

    while start < len(cleaned):
        end = min(start + chunk_size, len(cleaned))
        split_at = cleaned.rfind(". ", start, end)

        if split_at > start + chunk_size * 0.5:
            end = split_at + 1

        chunks.append(cleaned[start:end].strip())

        if end >= len(cleaned):
            break

        start = max(end - overlap, start + 1)

    return [chunk for chunk in chunks if chunk]


def normalize_spaces(text: str) -> str:
    return " ".join(text.split())


def normalize_figure_id(number: str) -> str:
    return f"Figure {number}"


def remove_captions_from_page_text(page_text: str, captions: list[FigureCaption]) -> str:
    cleaned = normalize_spaces(page_text)
    for caption in captions:
        cleaned = cleaned.replace(normalize_spaces(caption.caption), " ")
    return normalize_spaces(cleaned)


def clean_block_text(block_text: str, captions: list[FigureCaption]) -> str:
    cleaned = normalize_spaces(block_text)
    for caption in captions:
        caption_text = normalize_spaces(caption.caption)
        if cleaned == caption_text:
            return ""
        cleaned = cleaned.replace(caption_text, " ")
    return normalize_spaces(cleaned)


def is_low_quality_chunk(text: str) -> bool:
    cleaned = normalize_spaces(text)
    if len(cleaned) < 80:
        return True

    words = re.findall(r"[A-Za-z0-9]+", cleaned)
    if len(words) < 12:
        return True

    if "MNRAS 000" in cleaned and len(cleaned) < 220:
        return True

    letters = re.findall(r"[A-Za-z]", cleaned)
    if len(letters) < max(12, len(cleaned) * 0.08):
        return True

    return False


def is_section_heading(line: str) -> bool:
    stripped = line.strip()
    if re.match(r"^\d+(?:\.\d+)+\s*$", stripped):
        return True
    if re.match(r"^\d+(?:\.\d+)+\s+\S+", stripped):
        return True
    if re.match(r"^\d+\s+[A-Z][A-Z\s-]{6,}$", stripped):
        return True
    return False


def heading_kind(line: str) -> str | None:
    stripped = normalize_spaces(line).lower()
    if re.match(r"^\d+\s+introduction\b", stripped):
        return "introduction"
    if stripped == "introduction":
        return "introduction"

    if re.match(r"^\d+\s+(conclusions?|summary|discussion)\b", stripped):
        return "conclusion"
    if stripped in {
        "conclusion",
        "conclusions",
        "summary",
        "discussion",
        "summary and conclusions",
        "discussion and conclusions",
    }:
        return "conclusion"
    return None


def top_level_heading(line: str) -> bool:
    stripped = normalize_spaces(line)
    if re.match(r"^\d+\s+[A-Z][A-Za-z0-9, /&()-]+$", stripped):
        return True
    if re.match(r"^[A-Z][A-Z0-9, /&()-]{8,}$", stripped) and len(stripped.split()) <= 8:
        return True
    return False


def line_belongs_to_caption(line: str, page_captions: list[FigureCaption]) -> bool:
    cleaned_line = normalize_spaces(line)
    if not cleaned_line:
        return False
    return any(cleaned_line in normalize_spaces(caption.caption) for caption in page_captions)


def primary_figure_mention(line: str) -> tuple[str, int] | None:
    patterns = [
        r"\bIn\s+fig(?:ure)?\.?\s*(?P<number>\d+[A-Za-z]?)\s+we\s+"
        r"(?:show|present|plot|compare|display|illustrate|demonstrate|report)\b",
        r"\bfig(?:ure)?\.?\s*(?P<number>\d+[A-Za-z]?)\s+"
        r"(?:shows|presents|plots|compares|displays|illustrates|demonstrates|reports)\b",
        r"\bwe\s+(?:show|present|plot|compare|display|illustrate|demonstrate|report)"
        r".{0,180}?\bin\s+fig(?:ure)?\.?\s*(?P<number>\d+[A-Za-z]?)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, line, flags=re.IGNORECASE)
        if match is not None:
            return match.group("number"), match.start()
    return None


def build_primary_figure_discussion_chunks(
    pages: list[PageText],
    captions_by_page: dict[int, list[FigureCaption]],
    max_chars: int = 2800,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    seen: set[tuple[str, str]] = set()

    for page_index, page in enumerate(pages):
        lines = page.text.splitlines()

        for line_index, line in enumerate(lines):
            line_window = " ".join(lines[line_index: line_index + 3])
            primary = primary_figure_mention(line_window)
            if primary is None:
                continue

            figure_number, mention_start = primary
            figure_id = normalize_figure_id(figure_number)
            collected: list[str] = [line_window[mention_start:].strip()]
            stop_collection = False

            for next_page in pages[page_index: min(len(pages), page_index + 3)]:
                start_line = line_index + 3 if next_page.page == page.page else 0
                page_captions = captions_by_page.get(next_page.page, [])

                for next_line in next_page.text.splitlines()[start_line:]:
                    if is_section_heading(next_line) and len(normalize_spaces(" ".join(collected))) > 250:
                        stop_collection = True
                        break
                    if parse_caption_start(next_line) is not None:
                        continue
                    if line_belongs_to_caption(next_line, page_captions):
                        continue

                    cleaned_line = next_line.strip()
                    if not cleaned_line:
                        continue
                    if re.match(r"^\d+$", cleaned_line):
                        continue

                    collected.append(cleaned_line)
                    if len(normalize_spaces(" ".join(collected))) >= max_chars:
                        stop_collection = True
                        break

                discussion = normalize_spaces(" ".join(collected))
                if stop_collection or len(discussion) >= max_chars:
                    break

            discussion = normalize_spaces(" ".join(collected))
            if is_low_quality_chunk(discussion):
                continue

            key = (figure_id.lower(), discussion)
            if key in seen:
                continue
            seen.add(key)
            chunks.append(
                Chunk(
                    text=discussion,
                    page=page.page,
                    chunk_type="figure_discussion",
                    figure_id=figure_id,
                )
            )

    return chunks


def find_sentence_end(text: str, start: int, max_sentences: int = 5) -> int:
    end = len(text)
    sentence_count = 0
    for match in re.finditer(r"[.!?]\s+", text[start:]):
        sentence_count += 1
        if sentence_count >= max_sentences:
            end = start + match.end()
            break
    return end


def find_sentence_start(text: str, index: int) -> int:
    start = max(
        text.rfind(". ", 0, index),
        text.rfind("? ", 0, index),
        text.rfind("! ", 0, index),
    )
    if start == -1:
        return 0
    return start + 2


def build_figure_context_chunks(page: PageText, body_text: str) -> list[Chunk]:
    chunks: list[Chunk] = []
    seen: set[tuple[str, str]] = set()
    figure_re = re.compile(r"\bfig(?:ure)?\.?\s*(?P<number>\d+[A-Za-z]?)\b", re.IGNORECASE)

    for match in figure_re.finditer(body_text):
        number = match.group("number")
        start = find_sentence_start(body_text, match.start())
        end = find_sentence_end(body_text, start, max_sentences=8)
        context = normalize_spaces(body_text[start:end])
        if is_low_quality_chunk(context):
            continue

        figure_id = normalize_figure_id(number)
        key = (figure_id.lower(), context)
        if key in seen:
            continue
        seen.add(key)
        chunks.append(
            Chunk(
                text=context,
                page=page.page,
                chunk_type="figure_context",
                figure_id=figure_id,
            )
        )

    return chunks


def build_caption_followup_chunks(page: PageText, page_captions: list[FigureCaption]) -> list[Chunk]:
    if not page.blocks or not page_captions:
        return []

    chunks: list[Chunk] = []
    caption_by_text = {
        normalize_spaces(caption.caption): caption
        for caption in page_captions
    }

    for index, block in enumerate(page.blocks):
        caption = caption_by_text.get(normalize_spaces(block))
        if caption is None:
            continue

        followup_parts: list[str] = []
        for next_block in page.blocks[index + 1 : index + 4]:
            cleaned = clean_block_text(next_block, page_captions)
            if not cleaned:
                break
            if re.match(r"^(?:fig(?:ure)?\.?)\s*\d+", cleaned, flags=re.IGNORECASE):
                break
            if is_low_quality_chunk(cleaned):
                continue
            followup_parts.append(cleaned)
            if len(normalize_spaces(" ".join(followup_parts))) >= 500:
                break

        followup = normalize_spaces(" ".join(followup_parts))
        if is_low_quality_chunk(followup):
            continue
        chunks.append(
            Chunk(
                text=followup,
                page=page.page,
                chunk_type="figure_context",
                figure_id=caption.figure_id,
            )
        )

    return chunks


def build_global_context_chunks(
    pages: list[PageText],
    chunk_size: int = 1600,
    overlap: int = 120,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    current_kind: str | None = None
    current_page: int | None = None
    collected: list[str] = []

    def flush() -> None:
        nonlocal collected, current_kind, current_page
        if current_kind is None or current_page is None:
            collected = []
            return

        section_text = normalize_spaces(" ".join(collected))
        for text_chunk in split_text(section_text, chunk_size=chunk_size, overlap=overlap):
            if is_low_quality_chunk(text_chunk):
                continue
            chunks.append(
                Chunk(
                    text=text_chunk,
                    page=current_page,
                    chunk_type=current_kind,
                )
            )
        collected = []

    for page in pages:
        for line in page.text.splitlines():
            kind = heading_kind(line)
            if kind is not None:
                flush()
                current_kind = kind
                current_page = page.page
                collected = []
                continue

            if current_kind is not None and top_level_heading(line):
                flush()
                current_kind = None
                current_page = None
                continue

            if current_kind is None:
                continue

            cleaned_line = line.strip()
            if not cleaned_line or re.match(r"^\d+$", cleaned_line):
                continue
            collected.append(cleaned_line)

    flush()
    return chunks


def build_chunks(
    pages: list[PageText],
    captions: list[FigureCaption],
    chunk_size: int = 900,
    overlap: int = 120,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    captions_by_page: dict[int, list[FigureCaption]] = {}
    for caption in captions:
        captions_by_page.setdefault(caption.page, []).append(caption)

    chunks.extend(build_global_context_chunks(pages))
    chunks.extend(build_primary_figure_discussion_chunks(pages, captions_by_page))

    for page in pages:
        body_text = remove_captions_from_page_text(
            page.text,
            captions_by_page.get(page.page, []),
        )

        chunks.extend(build_figure_context_chunks(page, body_text))
        chunks.extend(build_caption_followup_chunks(page, captions_by_page.get(page.page, [])))

        body_sources = page.blocks if page.blocks else []
        for body_source in body_sources:
            cleaned_body_source = clean_block_text(
                body_source,
                captions_by_page.get(page.page, []),
            )
            if not cleaned_body_source:
                continue
            for text_chunk in split_text(cleaned_body_source, chunk_size=chunk_size, overlap=overlap):
                if is_low_quality_chunk(text_chunk):
                    continue
                chunks.append(
                    Chunk(
                        text=text_chunk,
                        page=page.page,
                        chunk_type="body",
                    )
                )

        if not page.blocks:
            for text_chunk in split_text(body_text, chunk_size=chunk_size, overlap=overlap):
                if is_low_quality_chunk(text_chunk):
                    continue
                chunks.append(
                    Chunk(
                        text=text_chunk,
                        page=page.page,
                        chunk_type="body",
                    )
                )

    for caption in captions:
        chunks.append(
            Chunk(
                text=caption.caption,
                page=caption.page,
                chunk_type="caption",
                figure_id=caption.figure_id,
            )
        )

    return chunks
