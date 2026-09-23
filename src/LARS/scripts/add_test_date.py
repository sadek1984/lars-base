"""
add_test_date.py
================
Adds a proper DATE column `test_date` to chemistry_tidy, parsed from the raw
text column "التاريخ" (DD/MM/YYYY). Idempotent: safe to re-run after every
data reload.

Default is DIAGNOSE ONLY (read-only). Nothing is written without --apply.

    python scripts/add_test_date.py            # inspect formats + problems
    python scripts/add_test_date.py --apply    # write test_date
    python scripts/build_sample_summary.py     # then rebuild the summary

Pipeline order after any reload:
    transform_chemistry_data.py -> add_test_date.py --apply -> build_sample_summary.py
"""
import argparse
import sys
from pathlib import Path

import duckdb

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "lars_data_demo.duckdb"
RAW = '"التاريخ"'

# Normalize: trim, Arabic-Indic digits -> ASCII, '-' and '.' separators -> '/'
CLEAN = (f"replace(replace(translate(trim(CAST({RAW} AS VARCHAR)), "
         f"'٠١٢٣٤٥٦٧٨٩', '0123456789'), '-', '/'), '.', '/')")
# Accepted formats, day-first (the lab's convention). Time part tolerated.
PARSED = (f"CAST(TRY_STRPTIME({CLEAN}, "
          f"['%d/%m/%Y', '%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M', '%Y/%m/%d']) AS DATE)")


def diagnose(con) -> int:
    print("── Raw format shapes (digits→9) ──")
    for shape, n in con.execute(f"""
        SELECT regexp_replace({CLEAN}, '[0-9]', '9', 'g') AS shape, COUNT(*)
        FROM chemistry_tidy GROUP BY 1 ORDER BY 2 DESC LIMIT 10
    """).fetchall():
        print(f"   {str(shape):<25} {n}")

    # Day-first sanity check: in DD/MM, the 2nd part must never exceed 12
    bad_month = con.execute(f"""
        SELECT COUNT(*) FROM chemistry_tidy
        WHERE regexp_matches({CLEAN}, '^\\d{{1,2}}/\\d{{1,2}}/\\d{{4}}')
          AND CAST(split_part({CLEAN}, '/', 2) AS INT) > 12
    """).fetchone()[0]
    day_gt_12 = con.execute(f"""
        SELECT COUNT(*) FROM chemistry_tidy
        WHERE regexp_matches({CLEAN}, '^\\d{{1,2}}/\\d{{1,2}}/\\d{{4}}')
          AND CAST(split_part({CLEAN}, '/', 1) AS INT) > 12
    """).fetchone()[0]
    print(f"\n── Day-first check ── rows with 1st part >12: {day_gt_12} (confirms DD/MM)"
          f" | rows with 2nd part >12: {bad_month} (must be 0)")

    total, parsed, empty, dmin, dmax = con.execute(f"""
        SELECT COUNT(*), COUNT({PARSED}),
               COUNT(*) FILTER (WHERE {RAW} IS NULL OR trim(CAST({RAW} AS VARCHAR)) = ''),
               MIN({PARSED}), MAX({PARSED})
        FROM chemistry_tidy
    """).fetchone()
    failed = total - parsed - empty
    print(f"\n── Parse result ── rows={total}  parsed={parsed}  empty={empty}  "
          f"UNPARSEABLE={failed}")
    print(f"   true date range: {dmin} → {dmax}")

    print("\n── Months (real order) ──")
    for m, n in con.execute(f"""
        SELECT strftime({PARSED}, '%Y-%m') AS m, COUNT(DISTINCT "كود العينة")
        FROM chemistry_tidy WHERE {PARSED} IS NOT NULL GROUP BY 1 ORDER BY 1
    """).fetchall():
        print(f"   {m}  {n} samples")

    rows = con.execute(f"""
        SELECT DISTINCT "كود العينة", {RAW}
        FROM chemistry_tidy WHERE {PARSED} IS NULL LIMIT 20
    """).fetchall()
    if rows:
        print("\n── Samples without a usable date (first 20) ──")
        for code, raw in rows:
            print(f"   {code}  raw={raw!r}")
    return bad_month


def apply(con) -> None:
    con.execute("ALTER TABLE chemistry_tidy ADD COLUMN IF NOT EXISTS test_date DATE")
    con.execute(f"UPDATE chemistry_tidy SET test_date = {PARSED}")
    n, nulls = con.execute(
        "SELECT COUNT(*), COUNT(*) - COUNT(test_date) FROM chemistry_tidy").fetchone()
    print(f"\n✅ test_date written: {n} rows, {nulls} NULL")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-path", type=Path, default=DEFAULT_DB)
    ap.add_argument("--apply", action="store_true", help="write the column (default: diagnose only)")
    a = ap.parse_args()
    if not a.db_path.exists():
        sys.exit(f"❌ DB not found: {a.db_path}")
    try:
        con = duckdb.connect(str(a.db_path), read_only=not a.apply)
    except duckdb.IOException as e:
        sys.exit(f"❌ Could not open (close DBeaver / the app first)\n   {e}")

    print(f"🗄️  {a.db_path}  ({'APPLY' if a.apply else 'diagnose only'})\n")
    bad = diagnose(con)
    if a.apply:
        if bad:
            sys.exit("❌ Refusing to write: some dates look MM/DD. Inspect them first.")
        apply(con)
    else:
        print("\nNothing written. Re-run with --apply if the numbers above look right.")
    con.close()