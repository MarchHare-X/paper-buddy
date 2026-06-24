from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import BinaryIO


@dataclass(frozen=True)
class PageText:
    page: int
    text: str
    blocks: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ParsedPDF:
    filename: str
    total_pages: int
    pages: list[PageText]
    title: str | None = None


def normalize_spaces(text: str) -> str:
    return " ".join(text.split())


def looks_like_title_candidate(text: str) -> bool:
    if len(text) < 20 or len(text) > 220:
        return False

    lowered = text.lower()
    noisy_markers = [
        "mnras",
        "accepted",
        "received",
        "arxiv",
        "abstract",
        "keywords",
        "doi",
    ]
    if any(marker in lowered for marker in noisy_markers):
        return False

    words = text.split()
    return len(words) >= 4


def infer_title(metadata_title: str | None, pages: list[PageText], filename: str) -> str | None:
    title = normalize_spaces(metadata_title or "")
    if looks_like_title_candidate(title):
        return title

    if pages:
        for block in pages[0].blocks[:8]:
            candidate = normalize_spaces(block)
            if looks_like_title_candidate(candidate):
                return candidate

    stem = Path(filename).stem
    if looks_like_title_candidate(stem):
        return stem
    return None


def parse_pdf(file: BinaryIO | str | Path, filename: str | None = None) -> ParsedPDF:
    """Parse a PDF into page-level text with 1-based page numbers."""
    import fitz

    if isinstance(file, (str, Path)):
        doc = fitz.open(str(file))
        resolved_filename = filename or Path(file).name
    else:
        data = file.read()
        doc = fitz.open(stream=data, filetype="pdf")
        resolved_filename = filename or getattr(file, "name", "uploaded.pdf")

    try:
        pages: list[PageText] = []
        for index, page in enumerate(doc):
            blocks = [
                " ".join(block[4].split())
                for block in sorted(page.get_text("blocks"), key=lambda item: (item[1], item[0]))
                if " ".join(block[4].split())
            ]
            pages.append(
                PageText(
                    page=index + 1,
                    text=page.get_text("text").strip(),
                    blocks=blocks,
                )
            )
        title = infer_title(doc.metadata.get("title"), pages, resolved_filename)
        return ParsedPDF(
            filename=resolved_filename,
            total_pages=doc.page_count,
            pages=pages,
            title=title,
        )
    finally:
        doc.close()
