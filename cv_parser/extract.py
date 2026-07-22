"""Raw-text extraction from the various CV file formats.

Each format has its own reader; the router picks one by extension. Heavy
dependencies (PDF/DOCX/OCR libraries) are imported lazily so the package still
imports and runs on .txt/.html files even when they aren't installed — the demo
degrades gracefully instead of crashing.
"""
from __future__ import annotations

import html
import re
from pathlib import Path


class ExtractionError(RuntimeError):
    """Raised when a file can't be read into text."""


def _read_txt(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _read_html(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    try:
        from bs4 import BeautifulSoup  # optional dependency
        return BeautifulSoup(raw, "html.parser").get_text("\n")
    except ImportError:
        # Fallback: strip tags with a regex so the demo works without bs4.
        text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", raw)
        text = re.sub(r"(?s)<[^>]+>", "\n", text)
        return html.unescape(text)


def _read_pdf(path: Path) -> str:
    try:
        import pdfplumber  # optional dependency
    except ImportError as exc:  # pragma: no cover - env dependent
        raise ExtractionError(
            "PDF support needs 'pdfplumber' (pip install pdfplumber)"
        ) from exc
    with pdfplumber.open(path) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def _read_docx(path: Path) -> str:
    try:
        import docx  # python-docx, optional dependency
    except ImportError as exc:  # pragma: no cover - env dependent
        raise ExtractionError(
            "DOCX support needs 'python-docx' (pip install python-docx)"
        ) from exc
    document = docx.Document(str(path))
    return "\n".join(p.text for p in document.paragraphs)


def _read_image(path: Path) -> str:
    """OCR path for scanned / JPG CVs.

    Real deployment uses Tesseract (or a cloud OCR); kept behind a lazy import
    so the rest of the pipeline runs without it.
    """
    try:
        import pytesseract  # optional dependency
        from PIL import Image  # optional dependency
    except ImportError as exc:  # pragma: no cover - env dependent
        raise ExtractionError(
            "Image/JPG OCR needs 'pytesseract' + 'Pillow' and the Tesseract binary"
        ) from exc
    return pytesseract.image_to_string(Image.open(path))


# Extension -> (reader, human-readable source label)
_READERS = {
    ".txt": (_read_txt, "Plain Text"),
    ".md": (_read_txt, "Plain Text"),
    ".html": (_read_html, "HTML Export"),
    ".htm": (_read_html, "HTML Export"),
    ".pdf": (_read_pdf, "PDF"),
    ".docx": (_read_docx, "DOCX"),
    ".jpg": (_read_image, "Image (OCR)"),
    ".jpeg": (_read_image, "Image (OCR)"),
    ".png": (_read_image, "Image (OCR)"),
}


def detect_file_type(path: Path) -> str:
    """Human-readable source label, used for the record's `fileType`."""
    reader = _READERS.get(path.suffix.lower())
    return reader[1] if reader else "Unknown"


def extract_text(path: Path) -> str:
    """Return the raw text of a CV file, or raise ExtractionError."""
    reader = _READERS.get(path.suffix.lower())
    if reader is None:
        raise ExtractionError(f"Unsupported file type: {path.suffix}")
    text = reader[0](path)
    if not text or not text.strip():
        raise ExtractionError("No text could be extracted (empty or scanned image?)")
    return text
