"""Field extraction: raw CV text -> the parsedData schema.

This demo uses transparent regex/heuristics so the logic is fully inspectable.
In production the same field slots are filled by an LLM/NER layer (spaCy or a
hosted model) for messy, unstructured CVs — the extraction strategy changes, but
the output schema in `schema.py` stays identical.
"""
from __future__ import annotations

import re
from typing import Any

from .schema import empty_parsed_data

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
# Loose international phone matcher; refined by length check below.
PHONE_RE = re.compile(r"(?:(?:\+|00)\d{1,3}[\s-]?)?(?:\(?\d{2,4}\)?[\s-]?){2,4}\d{2,4}")
LINKEDIN_RE = re.compile(r"(?:https?://)?(?:www\.)?linkedin\.com/in/[A-Za-z0-9_-]+", re.I)
URL_RE = re.compile(r"https?://[^\s)>\]]+", re.I)

# Common CV section headers -> the block of text under each one.
SECTION_HEADERS = {
    "summary": ["summary", "profile", "objective", "about"],
    "experience": ["experience", "work experience", "employment", "work history"],
    "education": ["education", "academic", "qualifications"],
    "skills": ["skills", "technical skills", "core competencies"],
    "languages": ["languages", "language"],
    "certifications": ["certifications", "certificates", "licenses"],
}


def _first(pattern: re.Pattern, text: str) -> str | None:
    match = pattern.search(text)
    return match.group(0).strip() if match else None


def _guess_name(text: str) -> str | None:
    """Heuristic: the first non-empty line that looks like a person's name."""
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        words = line.split()
        if 1 < len(words) <= 4 and all(w[:1].isalpha() for w in words) \
                and "@" not in line and not any(ch.isdigit() for ch in line):
            return line
        break  # only inspect the top of the document
    return None


def _extract_phone(text: str) -> str | None:
    for candidate in PHONE_RE.findall(text):
        digits = re.sub(r"\D", "", candidate)
        if 7 <= len(digits) <= 15:  # plausible phone length
            return candidate.strip()
    return None


def _split_sections(text: str) -> dict[str, str]:
    """Bucket lines into sections keyed by the headers they fall under."""
    buckets: dict[str, list[str]] = {}
    # Lines before any recognized header (name, contact block) land in
    # "_preamble" and are deliberately kept out of the summary field.
    current = "_preamble"
    for line in text.splitlines():
        stripped = line.strip().lower().rstrip(":")
        matched = next(
            (key for key, aliases in SECTION_HEADERS.items() if stripped in aliases),
            None,
        )
        if matched:
            current = matched
            continue
        buckets.setdefault(current, []).append(line)
    return {k: "\n".join(v).strip() for k, v in buckets.items()}


def _skills_from(block: str) -> list[dict[str, Any]]:
    if not block:
        return []
    tokens = [t.strip() for t in re.split(r"[,\n•|/]", block) if t.strip()]
    tokens = [t for t in tokens if 1 < len(t) <= 40][:40]
    if not tokens:
        return []
    return [{
        "category": "General",
        "skills": tokens,
        "yearsExperience": None,
        "proficiency": None,
    }]


def parse_text(text: str) -> dict[str, Any]:
    """Turn raw CV text into a fully-shaped parsedData object."""
    data = empty_parsed_data()
    pd = data["personalDetails"]

    pd["name"] = _guess_name(text)
    pd["email"] = _first(EMAIL_RE, text)
    pd["phone"] = _extract_phone(text)
    pd["linkedin"] = _first(LINKEDIN_RE, text)
    website = _first(URL_RE, text)
    if website and "linkedin.com" not in website.lower():
        pd["website"] = website

    sections = _split_sections(text)
    data["summary"] = sections.get("summary", "")[:1000]
    data["skills"] = _skills_from(sections.get("skills", ""))

    # workExperience / education / languages / certifications / projects are
    # left as empty lists here; the production NER layer populates them. The keys
    # are always present so downstream code and QA never have to guard for them.
    return data
