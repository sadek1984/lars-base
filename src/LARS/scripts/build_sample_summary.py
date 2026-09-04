"""
build_sample_summary.py
========================
Builds/rebuilds the sample_summary aggregate table from chemistry_tidy.
Run this after every data reload — sample_summary is a SNAPSHOT, not a
live view, and will go stale if chemistry_tidy changes underneath it.

Usage:
    python build_sample_summary.py [--db-path /path/to/lars_data_demo.duckdb]
"""
import argparse
import duckdb


def build(db_path: str) -> None:
    con = duckdb.connect(db_path, read_only=False)

    con.execute("DROP TABLE IF EXISTS sample_summary")
    con.execute("""
        CREATE TABLE sample_summary AS
        SELECT
            "كود العينة"   AS sample_code,
            ANY_VALUE("اسم العينة")   AS sample_name,
            ANY_VALUE("نوع العينة")   AS sample_category,
            ANY_VALUE("الحى")         AS neighborhood,
            ANY_VALUE("اسم البلدية")  AS municipality,
            ANY_VALUE("التاريخ")      AS sample_date,
            ANY_VALUE(sample_result)  AS sample_result,
            COUNT(CASE WHEN is_detected = 1 AND pesticide_name NOT IN ('NO DETECTION', 'NO DATA')
                       THEN 1 END)     AS residue_count,
            SUM(CASE WHEN is_above_limit = 1 THEN 1 ELSE 0 END) AS violation_count
        FROM chemistry_tidy
        GROUP BY "كود العينة"
    """)

    count = con.execute("SELECT COUNT(*) FROM sample_summary").fetchone()[0]
    print(f"✅ sample_summary built: {count} rows")
    con.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--db-path",
        default="/Users/a12/lars-base/src/LARS/data/lars_data_test_copy.duckdb",
        help="Path to the DuckDB file (use the TEST COPY for now, not production)",
    )
    args = parser.parse_args()
    build(args.db_path)