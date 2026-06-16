from __future__ import annotations

from dataclasses import dataclass

from .pdf_parser import PageText


@dataclass(frozen=True)
class FigureCaption:
    page: int
    figure_id: str
    caption: str


def normalize_figure_id(label: str, number: str) -> str:
    prefix = "Figure" if label.lower().startswith("figure") else "Fig."
    return f"{prefix} {number}"


def parse_caption_start(line: str) -> tuple[str, str] | None:
    """Return figure label and number when a line starts like a figure caption."""
    import re

    match = re.match(
        r"^\s*(?P<label>fig(?:ure)?\.?)\s*"
        r"(?P<number>\d+[A-Za-z]?)"
        r"\s*(?P<punct>[\.:])?\s+"
        r"(?P<body>.+)",
        line,
        flags=re.IGNORECASE,
    )
    if match is None:
        return None

    has_caption_punctuation = bool(match.group("punct")) or match.group("label").endswith(".")
    first_word = match.group("body").split(maxsplit=1)[0].strip(".,:;!?").lower()
    if not has_caption_punctuation and first_word in {"we", "shows", "show", "see", "present"}:
        return None

    return match.group("label"), match.group("number")


def looks_like_caption_continuation(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.startswith(("MNRAS ", "©", "http://", "https://")):
        return False
    if len(stripped) < 80 and stripped.isupper():
        return False
    return True


def clean_caption(text: str) -> str:
    return " ".join(text.split())


def extract_caption_from_block(page_number: int, block: str) -> FigureCaption | None:
    start = parse_caption_start(block)
    if start is None:
        return None

    label, number = start
    caption = clean_caption(block)
    return FigureCaption(
        page=page_number,
        figure_id=normalize_figure_id(label, number),
        caption=caption,
    )


def dedupe_captions(captions: list[FigureCaption]) -> list[FigureCaption]:
    seen: set[tuple[int, str, str]] = set()
    deduped: list[FigureCaption] = []
    for caption in captions:
        key = (caption.page, caption.figure_id.lower(), caption.caption)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(caption)
    return deduped


def extract_figure_captions(pages: list[PageText]) -> list[FigureCaption]:
    """Extract figure captions from page text using common paper caption patterns."""
    captions: list[FigureCaption] = []

    for page in pages:
        if page.blocks:
            for block in page.blocks:
                caption = extract_caption_from_block(page.page, block)
                if caption is not None:
                    captions.append(caption)
            continue

        lines = page.text.splitlines()
        index = 0

        while index < len(lines):
            start = parse_caption_start(lines[index])
            if start is None:
                index += 1
                continue

            label, number = start
            caption_lines = [lines[index].strip()]
            index += 1

            while index < len(lines):
                next_start = parse_caption_start(lines[index])
                if next_start is not None:
                    break
                if not looks_like_caption_continuation(lines[index]):
                    break
                caption_lines.append(lines[index].strip())
                if len(" ".join(caption_lines)) >= 900:
                    index += 1
                    break
                index += 1

            caption = clean_caption(" ".join(caption_lines))
            captions.append(
                FigureCaption(
                    page=page.page,
                    figure_id=normalize_figure_id(label, number),
                    caption=caption,
                )
            )

    return dedupe_captions(captions)
