"""
build_sample_summary.py
========================
Builds/rebuilds the sample_summary aggregate table from chemistry_tidy.
Run this after every data reload — sample_summary is a SNAPSHOT, not a
live view, and will go stale if chemistry_tidy changes underneath it.

Date handling:
  - If chemistry_tidy has a proper DATE column `test_date`, it is used.
  - Otherwise falls back to the raw "التاريخ" text column and WARNS,
    because date filters on sample_summary will then compare text, not dates.

Usage (no square brackets — they only mean "optional"):
    python build_sample_summary.py
    python build_sample_summary.py --db-path /Users/a12/lars-base/src/LARS/data/lars_data_test_copy.duckdb

Close DBeaver's connection to the file first: DuckDB allows only one writer.
"""
import argparse
import sys
from pathlib import Path

import duckdb

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "lars_data_demo.duckdb"


def pick_date_expr(con) -> str:
    cols = {r[0]: r[1].upper() for r in con.execute(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_name = 'chemistry_tidy'"
    ).fetchall()}

    if "test_date" in cols:
        if cols["test_date"] not in ("DATE", "TIMESTAMP"):
            print(f"⚠️  test_date exists but its type is {cols['test_date']}, casting with TRY_CAST")
            return "ANY_VALUE(TRY_CAST(test_date AS DATE))"
        print("📅 Using test_date (DATE)")
        return "ANY_VALUE(test_date::DATE)"

    print("⚠️  test_date NOT found in chemistry_tidy — falling back to raw \"التاريخ\" (text).")
    print("    Date filters on sample_summary will be unreliable until the ETL fix lands.")
    return 'ANY_VALUE("التاريخ")'


def build(db_path: Path) -> None:
    if not db_path.exists():
        sys.exit(f"❌ DB not found: {db_path}")
    try:
        con = duckdb.connect(str(db_path), read_only=False)
    except duckdb.IOException as e:
        sys.exit(f"❌ Could not open for writing (is DBeaver or the app connected?)\n   {e}")

    print(f"🗄️  Target: {db_path}")
    date_expr = pick_date_expr(con)

    con.execute("DROP TABLE IF EXISTS sample_summary")
    con.execute(f"""
        CREATE TABLE sample_summary AS
        SELECT
            "كود العينة"               AS sample_code,
            ANY_VALUE("اسم العينة")    AS sample_name,
            ANY_VALUE("نوع العينة")    AS sample_category,
            ANY_VALUE("الحى")          AS neighborhood,
            ANY_VALUE("اسم البلدية")   AS municipality,
            {date_expr}                AS sample_date,
            ANY_VALUE(sample_result)   AS sample_result,
            COUNT(CASE WHEN is_detected = 1
                        AND pesticide_name NOT IN ('NO DETECTION', 'NO DATA')
                       THEN 1 END)      AS residue_count,
            SUM(CASE WHEN is_above_limit = 1 THEN 1 ELSE 0 END) AS violation_count
        FROM chemistry_tidy
        GROUP BY "كود العينة"
    """)

    n, dtype, nulls, dmin, dmax = con.execute("""
        SELECT COUNT(*), typeof(ANY_VALUE(sample_date)),
               COUNT(*) - COUNT(sample_date), MIN(sample_date), MAX(sample_date)
        FROM sample_summary
    """).fetchone()
    print(f"✅ sample_summary built: {n} rows")
    print(f"   sample_date type={dtype}  range={dmin} → {dmax}  nulls={nulls}")
    if nulls:
        print(f"⚠️  {nulls} samples have no parseable date — check them before the demo.")
    con.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB,
                        help=f"DuckDB file (default: {DEFAULT_DB})")
    build(parser.parse_args().db_path)