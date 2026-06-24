from __future__ import annotations

import hashlib
import re


def file_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_filename(filename: str) -> str:
    stem = filename.strip() or "paper"
    stem = re.sub(r"\s+", "-", stem)
    stem = re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+", "-", stem)
    return stem.strip("-") or "paper"


def make_paper_id(filename: str, data: bytes) -> str:
    digest = file_sha256(data)
    return f"{safe_filename(filename)}::{digest[:16]}"
