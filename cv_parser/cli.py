"""Command-line entry point.

    python -m cv_parser.cli <file-or-folder> [-o output.json]

Prints a short QA summary to stderr and writes the schema-shaped JSON array to
the output file (default: parsed_output.json).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import parse_file, parse_folder


def _qa_summary(records: list[dict]) -> str:
    total = len(records)
    ok = sum(1 for r in records if r["status"] == "success")
    with_email = sum(1 for r in records if r["parsedData"]["personalDetails"]["email"])
    with_name = sum(1 for r in records if r["parsedData"]["personalDetails"]["name"])
    return (
        f"Parsed {total} file(s): {ok} success, {total - ok} failed | "
        f"name found: {with_name}/{total} | email found: {with_email}/{total}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Parse CV files into structured JSON.")
    parser.add_argument("input", help="A CV file or a folder of CVs")
    parser.add_argument("-o", "--output", default="parsed_output.json",
                        help="Output JSON path (default: parsed_output.json)")
    args = parser.parse_args(argv)

    source = Path(args.input)
    if not source.exists():
        print(f"error: {source} does not exist", file=sys.stderr)
        return 1

    records = parse_folder(source) if source.is_dir() else [parse_file(source)]

    Path(args.output).write_text(
        json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(_qa_summary(records), file=sys.stderr)
    print(f"Wrote {len(records)} record(s) -> {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
