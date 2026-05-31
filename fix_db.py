"""
fix_db.py  —  Run ONCE from your project root:
    python fix_db.py

Does two things:
  1. Trims leading/trailing whitespace from "اسم العينة" in chemistry_tidy
  2. Prints a report so you can see what changed
"""
import duckdb
from pathlib import Path

DB = Path("src/LARS/data/lars_data.duckdb")

if not DB.exists():
    raise FileNotFoundError(f"Database not found: {DB}")

con = duckdb.connect(str(DB))          # read-write

# ── 1. Show before ────────────────────────────────────────────
print("Before trim — distinct sample names with leading/trailing spaces:")
before = con.execute("""
    SELECT "اسم العينة", LENGTH("اسم العينة") as len
    FROM chemistry_tidy
    WHERE "اسم العينة" != TRIM("اسم العينة")
    GROUP BY "اسم العينة"
    ORDER BY "اسم العينة"
""").fetchall()
for row in before:
    print(f"  {repr(row[0])}  (len={row[1]})")
print(f"  Total dirty rows: {len(before)}")

# ── 2. Trim all whitespace ────────────────────────────────────
con.execute("""
    UPDATE chemistry_tidy
    SET "اسم العينة" = TRIM("اسم العينة")
    WHERE "اسم العينة" != TRIM("اسم العينة")
""")
print("\n✅ Trim applied.")

# ── 3. Verify ─────────────────────────────────────────────────
after = con.execute("""
    SELECT COUNT(*) FROM chemistry_tidy
    WHERE "اسم العينة" != TRIM("اسم العينة")
""").fetchone()[0]
print(f"Remaining dirty rows after trim: {after}  (should be 0)")

# ── 4. Show all distinct sample names now ────────────────────
all_names = con.execute("""
    SELECT "اسم العينة", COUNT(*) as n
    FROM chemistry_tidy
    GROUP BY "اسم العينة"
    ORDER BY n DESC
""").fetchall()
print(f"\nAll distinct sample names ({len(all_names)} total):")
for name, n in all_names:
    print(f"  {repr(name):40s}  rows={n}")

con.close()
print("\nDone. Now run the engine test again.")