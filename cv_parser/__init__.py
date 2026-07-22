"""Minimal CV -> structured JSON parser (demo).

Public API:
    parse_file(path)  -> one record dict matching the target schema
    parse_folder(dir) -> list of records (the full output array)
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .extract import ExtractionError, detect_file_type, extract_text
from .parse import parse_text
from .schema import empty_record

__all__ = ["parse_file", "parse_folder", "ExtractionError"]

SUPPORTED_SUFFIXES = {".txt", ".md", ".html", ".htm", ".pdf", ".docx",
                      ".jpg", ".jpeg", ".png"}


def _human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB"):
        if size < 1024 or unit == "MB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} MB"


def parse_file(path: str | Path, index: int = 0) -> dict[str, Any]:
    """Parse a single CV into one schema record. Never raises: on failure it
    returns a record with status='failed' so a batch run isn't interrupted by
    one bad file."""
    path = Path(path)
    record = empty_record()
    record["id"] = f"offline_{int(time.time())}_{index}"
    record["fileName"] = path.name
    record["fileType"] = detect_file_type(path)
    try:
        record["fileSize"] = _human_size(path.stat().st_size)
        text = extract_text(path)
        record["text"] = text
        record["parsedData"] = parse_text(text)
        record["status"] = "success"
    except (ExtractionError, OSError) as exc:
        record["status"] = "failed"
        record["text"] = f"[extraction error] {exc}"
    return record


def parse_folder(directory: str | Path) -> list[dict[str, Any]]:
    """Parse every supported CV in a folder into the output array."""
    directory = Path(directory)
    files = sorted(
        p for p in directory.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES
    )
    return [parse_file(p, i) for i, p in enumerate(files)]
