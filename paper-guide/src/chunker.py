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
    section: str | None = None
    section_title: str | None = None
    paragraph_id: int | None = None
    source_block: int | None = None
    quality_score: float = 1.0
    paper_title: str | None = None


@dataclass(frozen=True)
class BodyBlock:
    text: str
    page: int
    source_block: int | None
    section: str | None
    section_title: str | None


def sentence_chunks(
    sentences: list[str],
    chunk_size: int,
    sentence_overlap: int = 1,
) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []

    for sentence in sentences:
        candidate = normalize_spaces(" ".join(current + [sentence]))
        if current and len(candidate) > chunk_size:
            chunks.append(normalize_spaces(" ".join(current)))
            current = current[-sentence_overlap:] if sentence_overlap > 0 else []

        current.append(sentence)

    if current:
        chunks.append(normalize_spaces(" ".join(current)))

    return chunks


def split_sentences(text: str) -> list[str]:
    cleaned = normalize_spaces(text)
    if not cleaned:
        return []

    sentence_end_re = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'“‘(])")
    sentences = [part.strip() for part in sentence_end_re.split(cleaned) if part.strip()]
    return sentences or [cleaned]


def split_text(text: str, chunk_size: int = 900, overlap: int = 1) -> list[str]:
    cleaned = " ".join(text.split())
    if not cleaned:
        return []

    sentences = split_sentences(cleaned)
    return sentence_chunks(sentences, chunk_size=chunk_size, sentence_overlap=overlap)


def normalize_spaces(text: str) -> str:
    return " ".join(text.split())


def normalize_figure_id(number: str) -> str:
    return f"Figure {number}"


LEADING_FRAGMENT_STARTS = {
    "and",
    "as",
    "at",
    "by",
    "for",
    "from",
    "in",
    "into",
    "of",
    "on",
    "or",
    "than",
    "that",
    "to",
    "with",
    "within",
    "without",
}


def looks_like_leading_fragment(text: str) -> bool:
    cleaned = normalize_spaces(text)
    match = re.match(r"^[A-Za-z]+", cleaned)
    if match is None:
        return False
    first_word = match.group(0)
    return first_word.islower() and first_word.lower() in LEADING_FRAGMENT_STARTS


def repair_chunk_boundaries(text: str) -> str:
    cleaned = normalize_spaces(text)
    if not cleaned:
        return ""

    first_word = re.match(r"^[A-Za-z]+", cleaned)
    starts_with_lowercase_word = bool(first_word and first_word.group(0)[0].islower())
    if starts_with_lowercase_word or looks_like_leading_fragment(cleaned):
        sentence_end = re.search(r"[.!?]\s+", cleaned)
        if sentence_end is not None and sentence_end.end() < len(cleaned):
            cleaned = cleaned[sentence_end.end() :].strip()

    if not re.search(r"[.!?]$|[\u3002\uff01\uff1f]$", cleaned):
        sentence_ends = list(re.finditer(r"[.!?](?=\s|$)", cleaned))
        if sentence_ends:
            cleaned = cleaned[: sentence_ends[-1].end()].strip()

    return cleaned


def ends_with_sentence_boundary(text: str) -> bool:
    return bool(re.search(r"[.!?]$|[\u3002\uff01\uff1f]$", normalize_spaces(text)))


def should_merge_body_blocks(previous: BodyBlock, current: BodyBlock) -> bool:
    if previous.section_title != current.section_title:
        return False
    if ends_with_sentence_boundary(previous.text):
        return False
    return looks_like_leading_fragment(current.text)


def merge_cross_page_body_blocks(blocks: list[BodyBlock]) -> list[BodyBlock]:
    if not blocks:
        return []

    merged: list[BodyBlock] = []
    current = blocks[0]

    for next_block in blocks[1:]:
        if should_merge_body_blocks(current, next_block):
            current = BodyBlock(
                text=normalize_spaces(f"{current.text} {next_block.text}"),
                page=current.page,
                source_block=current.source_block,
                section=current.section,
                section_title=current.section_title,
            )
            continue

        merged.append(current)
        current = next_block

    merged.append(current)
    return merged


def quality_score(text: str) -> float:
    cleaned = normalize_spaces(text)
    if not cleaned:
        return 0.0

    score = 1.0
    first_word = re.match(r"^[A-Za-z]+", cleaned)
    if first_word and first_word.group(0)[0].islower():
        score -= 0.18
    if re.match(r"^[,;:)\]}]", cleaned):
        score -= 0.25
    if not re.search(r"[.!?]$|[\u3002\uff01\uff1f]$", cleaned):
        score -= 0.10
    if len(cleaned) < 160:
        score -= 0.10
    if "MNRAS 000" in cleaned:
        score -= 0.20

    words = re.findall(r"[A-Za-z0-9]+", cleaned)
    short_words = [word for word in words if len(word) <= 2]
    if words and len(short_words) / len(words) > 0.45:
        score -= 0.10

    return max(0.0, min(1.0, score))


def make_chunk(
    text: str,
    page: int,
    chunk_type: str,
    figure_id: str | None = None,
    section: str | None = None,
    section_title: str | None = None,
    paragraph_id: int | None = None,
    source_block: int | None = None,
    paper_title: str | None = None,
) -> Chunk:
    repaired_text = repair_chunk_boundaries(text)
    return Chunk(
        text=repaired_text,
        page=page,
        chunk_type=chunk_type,
        figure_id=figure_id,
        section=section,
        section_title=section_title,
        paragraph_id=paragraph_id,
        source_block=source_block,
        quality_score=quality_score(repaired_text),
        paper_title=paper_title,
    )


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


def is_page_artifact(text: str) -> bool:
    cleaned = normalize_spaces(text)
    if not cleaned:
        return True
    if re.match(r"^\d+\s+[A-Z][A-Za-z&\s.-]{2,40}$", cleaned):
        return True
    if re.match(r"^[A-Z][A-Za-z\s-]{2,50}\s+\d+$", cleaned):
        return True
    if re.match(r"^MNRAS\s+\d+", cleaned):
        return True
    return False


def is_section_heading(line: str) -> bool:
    stripped = line.strip()
    if re.match(r"^\d+(?:\.\d+)+\s*$", stripped):
        return True
    if re.match(r"^\d+(?:\.\d+)+\s+[A-Z][A-Za-z][A-Za-z0-9, /&()-]+$", stripped):
        return True
    if re.match(r"^\d+\s+[A-Z][A-Z\s-]{6,}$", stripped):
        return True
    return False


def heading_kind(line: str) -> str | None:
    stripped = normalize_spaces(line).lower()
    if re.match(r"^\d*\s*references\b", stripped) or stripped == "references":
        return "references"

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


def classify_section_title(title: str) -> str:
    lowered = normalize_spaces(title).lower()
    if "references" in lowered:
        return "references"
    if "introduction" in lowered:
        return "introduction"
    if any(word in lowered for word in ["conclusion", "summary", "discussion"]):
        return "conclusion"
    if any(word in lowered for word in ["method", "simulation", "data", "sample"]):
        return "methods"
    if any(word in lowered for word in ["result", "profile", "radius", "boundary"]):
        return "results"
    return "section"


def extract_heading_title(line: str) -> str:
    stripped = normalize_spaces(line)
    if re.match(r"^\d+(?:\.\d+)*\.?$", stripped):
        return ""
    return re.sub(r"^\d+(?:\.\d+)*\s+", "", stripped).strip()


def page_section_map(pages: list[PageText]) -> dict[int, tuple[str | None, str | None]]:
    sections: dict[int, tuple[str | None, str | None]] = {}
    current_section: str | None = None
    current_title: str | None = None

    for page in pages:
        for line in page.text.splitlines():
            if top_level_heading(line) or is_section_heading(line):
                title = extract_heading_title(line)
                if title:
                    current_title = title
                    current_section = heading_kind(line) or classify_section_title(title)
        sections[page.page] = (current_section, current_title)

    return sections


def is_reference_section(section: str | None, section_title: str | None) -> bool:
    if section == "references":
        return True
    return "references" in normalize_spaces(section_title or "").lower()


def top_level_heading(line: str) -> bool:
    stripped = normalize_spaces(line)
    if re.match(r"^\d+\s+[A-Z][A-Z0-9, /&()-]{6,}$", stripped):
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
    sections_by_page: dict[int, tuple[str | None, str | None]],
    paper_title: str | None,
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
                make_chunk(
                    text=discussion,
                    page=page.page,
                    chunk_type="figure_discussion",
                    figure_id=figure_id,
                    section=sections_by_page.get(page.page, (None, None))[0],
                    section_title=sections_by_page.get(page.page, (None, None))[1],
                    paper_title=paper_title,
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


def build_figure_context_chunks(
    page: PageText,
    body_text: str,
    section: str | None,
    section_title: str | None,
    paper_title: str | None,
) -> list[Chunk]:
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
            make_chunk(
                text=context,
                page=page.page,
                chunk_type="figure_context",
                figure_id=figure_id,
                section=section,
                section_title=section_title,
                paper_title=paper_title,
            )
        )

    return chunks


def build_caption_followup_chunks(
    page: PageText,
    page_captions: list[FigureCaption],
    section: str | None,
    section_title: str | None,
    paper_title: str | None,
) -> list[Chunk]:
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
            make_chunk(
                text=followup,
                page=page.page,
                chunk_type="figure_context",
                figure_id=caption.figure_id,
                section=section,
                section_title=section_title,
                source_block=index + 1,
                paper_title=paper_title,
            )
        )

    return chunks


def build_global_context_chunks(
    pages: list[PageText],
    chunk_size: int = 1600,
    overlap: int = 1,
    paper_title: str | None = None,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    current_kind: str | None = None
    current_title: str | None = None
    current_page: int | None = None
    collected: list[str] = []

    def flush() -> None:
        nonlocal collected, current_kind, current_title, current_page
        if current_kind is None or current_page is None:
            collected = []
            return

        section_text = normalize_spaces(" ".join(collected))
        for paragraph_id, text_chunk in enumerate(
            split_text(section_text, chunk_size=chunk_size, overlap=overlap),
            start=1,
        ):
            if is_low_quality_chunk(text_chunk):
                continue
            chunks.append(
                make_chunk(
                    text=text_chunk,
                    page=current_page,
                    chunk_type=current_kind,
                    section=current_kind,
                    section_title=current_title,
                    paragraph_id=paragraph_id,
                    paper_title=paper_title,
                )
            )
        collected = []

    for page in pages:
        for line in page.text.splitlines():
            kind = heading_kind(line)
            if kind is not None:
                flush()
                if kind == "references":
                    current_kind = None
                    current_title = None
                    current_page = None
                    collected = []
                    continue
                current_kind = kind
                current_title = extract_heading_title(line) or kind
                current_page = page.page
                collected = []
                continue

            if current_kind is not None and top_level_heading(line):
                flush()
                current_kind = None
                current_title = None
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


def collect_body_blocks(
    pages: list[PageText],
    captions_by_page: dict[int, list[FigureCaption]],
    sections_by_page: dict[int, tuple[str | None, str | None]],
) -> list[BodyBlock]:
    blocks: list[BodyBlock] = []

    for page in pages:
        section, section_title = sections_by_page.get(page.page, (None, None))

        if page.blocks:
            for source_block, body_source in enumerate(page.blocks, start=1):
                cleaned_body_source = clean_block_text(
                    body_source,
                    captions_by_page.get(page.page, []),
                )
                if not cleaned_body_source:
                    continue
                if is_reference_section(section, section_title):
                    continue
                if is_page_artifact(cleaned_body_source):
                    continue
                if top_level_heading(cleaned_body_source) or is_section_heading(cleaned_body_source):
                    continue
                if parse_caption_start(cleaned_body_source) is not None:
                    continue
                blocks.append(
                    BodyBlock(
                        text=cleaned_body_source,
                        page=page.page,
                        source_block=source_block,
                        section=section,
                        section_title=section_title,
                    )
                )
            continue

        body_text = remove_captions_from_page_text(
            page.text,
            captions_by_page.get(page.page, []),
        )
        if body_text:
            blocks.append(
                BodyBlock(
                    text=body_text,
                    page=page.page,
                    source_block=None,
                    section=section,
                    section_title=section_title,
                )
            )

    return blocks


def build_body_chunks(
    pages: list[PageText],
    captions_by_page: dict[int, list[FigureCaption]],
    sections_by_page: dict[int, tuple[str | None, str | None]],
    chunk_size: int,
    overlap: int,
    paper_title: str | None,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    paragraph_counts: dict[tuple[int, int | None], int] = {}
    body_blocks = merge_cross_page_body_blocks(
        collect_body_blocks(pages, captions_by_page, sections_by_page)
    )

    for body_block in body_blocks:
        key = (body_block.page, body_block.source_block)
        for text_chunk in split_text(body_block.text, chunk_size=chunk_size, overlap=overlap):
            if is_low_quality_chunk(text_chunk):
                continue
            paragraph_counts[key] = paragraph_counts.get(key, 0) + 1
            chunks.append(
                make_chunk(
                    text=text_chunk,
                    page=body_block.page,
                    chunk_type="body",
                    section=body_block.section,
                    section_title=body_block.section_title,
                    paragraph_id=paragraph_counts[key],
                    source_block=body_block.source_block,
                    paper_title=paper_title,
                )
            )

    return chunks


def build_chunks(
    pages: list[PageText],
    captions: list[FigureCaption],
    chunk_size: int = 900,
    overlap: int = 1,
    paper_title: str | None = None,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    captions_by_page: dict[int, list[FigureCaption]] = {}
    for caption in captions:
        captions_by_page.setdefault(caption.page, []).append(caption)

    sections_by_page = page_section_map(pages)

    chunks.extend(build_global_context_chunks(pages, paper_title=paper_title))
    chunks.extend(
        build_primary_figure_discussion_chunks(
            pages,
            captions_by_page,
            sections_by_page=sections_by_page,
            paper_title=paper_title,
        )
    )

    for page in pages:
        section, section_title = sections_by_page.get(page.page, (None, None))
        body_text = remove_captions_from_page_text(
            page.text,
            captions_by_page.get(page.page, []),
        )

        chunks.extend(
            build_figure_context_chunks(
                page,
                body_text,
                section=section,
                section_title=section_title,
                paper_title=paper_title,
            )
        )
        chunks.extend(
            build_caption_followup_chunks(
                page,
                captions_by_page.get(page.page, []),
                section=section,
                section_title=section_title,
                paper_title=paper_title,
            )
        )

    chunks.extend(
        build_body_chunks(
            pages,
            captions_by_page,
            sections_by_page,
            chunk_size=chunk_size,
            overlap=overlap,
            paper_title=paper_title,
        )
    )

    for caption in captions:
        section, section_title = sections_by_page.get(caption.page, (None, None))
        chunks.append(
            make_chunk(
                text=caption.caption,
                page=caption.page,
                chunk_type="caption",
                figure_id=caption.figure_id,
                section=section,
                section_title=section_title,
                paper_title=paper_title,
            )
        )

    return chunks
