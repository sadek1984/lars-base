"""
diff_against_baseline.py
==========================
Compares a new harness run against baseline.csv and flags anything that
changed status, tier, handler, or row_count. Use this after every phase
(1 through 4) — the gate is: no unexplained regressions.

Usage:
    python diff_against_baseline.py baseline.csv new_run.csv
"""

import csv
import sys
from pathlib import Path


def load(path):
    with Path(path).open(encoding="utf-8") as f:
        return {row["id"]: row for row in csv.DictReader(f)}


def main():
    if len(sys.argv) != 3:
        print("Usage: python diff_against_baseline.py <baseline.csv> <new_run.csv>")
        sys.exit(1)

    old = load(sys.argv[1])
    new = load(sys.argv[2])

    watch_fields = ["status", "tier_hit", "handler", "row_count"]

    regressions, improvements, unchanged = [], [], 0
    missing_in_new = set(old) - set(new)
    new_ids = set(new) - set(old)

    for qid, old_row in old.items():
        if qid not in new:
            continue
        new_row = new[qid]
        changed = {k: (old_row[k], new_row[k]) for k in watch_fields if old_row[k] != new_row[k]}
        if not changed:
            unchanged += 1
            continue

        was_broken = old_row["status"] == "exception" or old_row["row_count"] in ("0", "")
        now_broken = new_row["status"] == "exception" or new_row["row_count"] in ("0", "")

        entry = {"id": qid, "question": old_row["question"][:80], "changes": changed}
        if now_broken and not was_broken:
            regressions.append(entry)
        elif was_broken and not now_broken:
            improvements.append(entry)
        else:
            # changed but neither newly broken nor newly fixed (e.g. tier
            # moved from LLM to deterministic on a query that always worked)
            improvements.append(entry)

    print(f"Unchanged: {unchanged}")
    print(f"Changed (non-regression): {len(improvements)}")
    print(f"REGRESSIONS: {len(regressions)}")
    if missing_in_new:
        print(f"Missing from new run: {sorted(missing_in_new)}")
    if new_ids:
        print(f"New IDs not in baseline: {sorted(new_ids)}")

    if regressions:
        print("\n--- REGRESSIONS (fix before deploying) ---")
        for r in regressions:
            print(f"  [{r['id']}] {r['question']}")
            for field, (o, n) in r["changes"].items():
                print(f"      {field}: {o!r} -> {n!r}")

    if improvements:
        print("\n--- Changed, not regressions ---")
        for r in improvements[:20]:
            print(f"  [{r['id']}] {r['question']}")
            for field, (o, n) in r["changes"].items():
                print(f"      {field}: {o!r} -> {n!r}")
        if len(improvements) > 20:
            print(f"  ... and {len(improvements) - 20} more")


if __name__ == "__main__":
    main()
