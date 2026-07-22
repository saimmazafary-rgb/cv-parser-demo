# CV Parser — multi-format CV → structured JSON

A small, readable Python utility that parses CVs in multiple formats
(**PDF, DOCX, HTML, TXT, and JPG/scanned via OCR**) and emits a **structured
JSON array ready to save into a database**.

This is a focused demo of a document-extraction pipeline: format detection →
text extraction → field parsing → schema-shaped output → QA summary. The output
matches a fixed candidate schema exactly, so records drop straight into storage
with no remapping.

---

## Why it's built this way

- **One stable output schema.** Every record always has the same keys (see
  [`cv_parser/schema.py`](cv_parser/schema.py)); missing values are `null`/`[]`,
  never absent. Downstream code and QA can rely on the shape instead of guarding
  every field access.
- **Format router with graceful degradation.** Heavy libraries (PDF/DOCX/OCR)
  are imported lazily, so the tool runs on `.txt`/`.html` even before you install
  extras — and a single unreadable file is marked `status: "failed"` instead of
  crashing a batch of thousands.
- **Transparent extraction.** This demo fills fields with inspectable
  regex/heuristics. In production the same field slots are populated by an
  LLM/NER layer for messy, unstructured CVs — **the extraction strategy scales
  up, the output schema stays identical.**

---

## Install

```bash
git clone <your-repo-url>
cd cv-parser-demo
python3 -m pip install -r requirements.txt   # optional: enables PDF/DOCX/OCR
```

The core runs on the standard library alone for `.txt` and `.html` files.

## Usage

Parse a single CV:

```bash
python3 -m cv_parser.cli samples/jane_doe_cv.txt -o out.json
```

Parse a whole folder (the real use case — thousands of files):

```bash
python3 -m cv_parser.cli ./cvs -o parsed_output.json
```

Each run prints a QA summary to stderr, e.g.:

```
Parsed 1 file(s): 1 success, 0 failed | name found: 1/1 | email found: 1/1
```

Use it as a library:

```python
from cv_parser import parse_folder
records = parse_folder("./cvs")   # list of schema-shaped dicts
```

## Example output

Running it on [`samples/jane_doe_cv.txt`](samples/jane_doe_cv.txt) produces
[`examples/sample_output.json`](examples/sample_output.json) — one record shaped like:

```json
{
  "id": "offline_1784747782_0",
  "fileName": "jane_doe_cv.txt",
  "fileSize": "757.0 B",
  "fileType": "Plain Text",
  "text": "Jane Doe\nSenior Product Designer ...",
  "status": "success",
  "parsedData": {
    "personalDetails": {
      "name": "Jane Doe",
      "email": "jane.doe@example.com",
      "phone": "+965 5012 3456",
      "linkedin": "linkedin.com/in/janedoe",
      "website": "https://janedoe.design",
      "passportNo": null, "civilId": null, "visaNumber": null
      /* 19 fields total, always present */
    },
    "summary": "Product designer with 8 years of experience ...",
    "workExperience": [],
    "education": [],
    "skills": [{ "category": "General", "skills": ["Figma", "UX Research", "..."] }],
    "languages": [],
    "projects": [],
    "certifications": [],
    "preferences": { "preferredJobTitle": null, "expectedSalary": null }
  },
  "selected": false,
  "onboarded": false
}
```

## Supported formats

| Format | Extension | Method | Extra dependency |
|--------|-----------|--------|------------------|
| Plain text | `.txt`, `.md` | native | — |
| HTML | `.html`, `.htm` | tag strip / BeautifulSoup | `beautifulsoup4` (optional) |
| PDF | `.pdf` | text extraction | `pdfplumber` |
| Word | `.docx` | paragraph extraction | `python-docx` |
| Image / scanned | `.jpg`, `.jpeg`, `.png` | OCR | `pytesseract` + `Pillow` + Tesseract |

## Output schema

`parsedData` fields:

| Field | Type | Notes |
|-------|------|-------|
| `personalDetails` | object | 19 fields incl. contact + region fields (`passportNo`, `civilId`, `visaNumber`, …) |
| `summary` | string | professional profile paragraph |
| `workExperience` | list | `{company, role, startDate, endDate, description}` |
| `education` | list | `{institution, degree, major, cgpa, endDate}` |
| `skills` | list | `{category, skills[], yearsExperience, proficiency}` |
| `languages` | list | `{languageName, speakingLevel, readingLevel, writingLevel}` |
| `projects` | list | `{name, description, technologies}` |
| `certifications` | list | `{certificateName, issuer, issueDate, expiryDate}` |
| `preferences` | object | `{preferredJobTitle, expectedSalary, salaryCurrency, availabilityDate}` |

## Quality assurance

- Per-file `status` (`success` / `failed`) so batch runs never halt on one bad file.
- Per-field coverage reported each run (e.g. how many records got a name/email).
- Format-specific readers isolated in [`cv_parser/extract.py`](cv_parser/extract.py)
  so each can be tested against a gold set of hand-verified CVs.
- Stable schema means output can be diffed against expected records to catch regressions.

## Project layout

```
cv_parser/
  schema.py    # the output contract (single source of truth)
  extract.py   # format detection + text extraction (lazy deps)
  parse.py     # text -> parsedData fields
  cli.py       # command-line entry + QA summary
  __init__.py  # parse_file() / parse_folder()
samples/       # example input CV
examples/      # example output JSON
```

## Roadmap (production hardening)

- LLM/NER extraction layer for `workExperience`, `education`, `projects` from
  free-form CVs.
- Direct database sink (e.g. Django models) instead of a JSON file.
- Confidence scores per field + a manual-review queue for low-confidence parses.
- Parallel/batched processing for large volumes.

---

*Demo utility — extraction logic is intentionally simple and inspectable.*
