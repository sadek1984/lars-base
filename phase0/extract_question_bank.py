"""
extract_question_bank.py
=========================
Parses the pipe-table question bank (Groups A-E, IDs like A001, B012, C003,
D020, E035) out of LARS_Master_Spec_v2.md and writes a flat CSV that the
test harness (run_question_bank.py) consumes.

Usage:
    python extract_question_bank.py /path/to/LARS_Master_Spec_v2.md questions_bank.csv

The spec's tables look like:
    | E034 | ما هو ... السؤال بالعربي ... | English translation | tags, more tags |

This script does NOT assume a fixed column count beyond ID + at least one
question column, because Groups A-E were built in separate passes in the
source conversation and may have minor formatting drift. It keeps every
extra column it finds as tag_1, tag_2, ...
"""

import csv
import re
import sys
from pathlib import Path

ID_PATTERN = re.compile(r"^[A-E]\d{3}$")


def parse_markdown_tables(md_text: str):
    """
    Walk every pipe-table row in the document. Keep rows whose first cell
    matches an ID like A001-E999. Skip header/separator rows automatically
    since they won't match ID_PATTERN.
    """
    rows = []
    for line in md_text.splitlines():
        line = line.strip()
        if not line.startswith("|") or not line.endswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if not cells or not ID_PATTERN.match(cells[0]):
            continue
        rows.append(cells)
    return rows


def main():
    if len(sys.argv) != 3:
        print("Usage: python extract_question_bank.py <spec.md> <out.csv>")
        sys.exit(1)

    src = Path(sys.argv[1])
    dst = Path(sys.argv[2])

    if not src.exists():
        print(f"ERROR: {src} not found. Point this at your saved LARS_Master_Spec_v2.md")
        sys.exit(1)

    md_text = src.read_text(encoding="utf-8")
    rows = parse_markdown_tables(md_text)

    if not rows:
        print("WARNING: extracted 0 rows. The table format in your saved copy "
              "may differ from what this parser expects (pipe-delimited rows "
              "starting with an ID cell like A001). Open the .md and check "
              "sections 2.1-2.5 manually, then adjust ID_PATTERN or the "
              "column split above.")
        sys.exit(1)

    max_cols = max(len(r) for r in rows)
    fieldnames = ["id", "question"] + [f"extra_{i}" for i in range(max_cols - 2)]

    seen_ids = set()
    with dst.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            qid = r[0]
            if qid in seen_ids:
                # duplicate ID -> the parser likely caught a re-rendered
                # table fragment from the same source conversation. Keep
                # the first occurrence only.
                continue
            seen_ids.add(qid)
            record = {"id": qid, "question": r[1] if len(r) > 1 else ""}
            for i, extra in enumerate(r[2:]):
                record[f"extra_{i}"] = extra
            writer.writerow(record)

    print(f"Extracted {len(seen_ids)} unique questions -> {dst}")
    by_group = {}
    for qid in seen_ids:
        by_group[qid[0]] = by_group.get(qid[0], 0) + 1
    for g in sorted(by_group):
        print(f"  Group {g}: {by_group[g]}")
    if len(seen_ids) != 220:
        print(f"NOTE: expected 220, got {len(seen_ids)}. Some questions may "
              f"live in a table format this parser missed (e.g. a row that "
              f"wraps across lines) — spot-check the .md before trusting the "
              f"harness run as complete.")


if __name__ == "__main__":
    main()
