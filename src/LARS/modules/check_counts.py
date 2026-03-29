import duckdb
import pandas as pd

db_path = '/Users/a12/Buraidah_lars/src/LARS/data/lars_data.duckdb'
con = duckdb.connect(db_path, read_only=True)

# 1. Total samples with 10 detections (strict)
query1 = """
SELECT COUNT(*) as num_samples FROM (
    SELECT "كود العينة"
    FROM chemistry_tidy
    WHERE is_detected = 1 AND pesticide_name NOT IN ('NO DETECTION', 'NO DATA')
    GROUP BY "كود العينة"
    HAVING COUNT(*) = 10
)
"""
print("Query 1 (Current logic):", con.execute(query1).fetchone()[0])

# 2. Total samples with 10 detections (counting distinct pesticides)
query2 = """
SELECT COUNT(*) as num_samples FROM (
    SELECT "كود العينة"
    FROM chemistry_tidy
    WHERE is_detected = 1 AND pesticide_name NOT IN ('NO DETECTION', 'NO DATA')
    GROUP BY "كود العينة"
    HAVING COUNT(DISTINCT pesticide_name) = 10
)
"""
print("Query 2 (Distinct pesticides):", con.execute(query2).fetchone()[0])

# 3. Total samples with 10 entries (ignoring is_detected flag but keeping non-null names)
query3 = """
SELECT COUNT(*) as num_samples FROM (
    SELECT "كود العينة"
    FROM chemistry_tidy
    WHERE pesticide_name NOT IN ('NO DETECTION', 'NO DATA', 'NONE', 'N/A') AND pesticide_name IS NOT NULL
    GROUP BY "كود العينة"
    HAVING COUNT(*) = 10
)
"""
print("Query 3 (Ignoring is_detected):", con.execute(query3).fetchone()[0])

# 4. Check if some samples have COUNT > 10
query4 = """
SELECT COUNT(*) as num_samples FROM (
    SELECT "كود العينة"
    FROM chemistry_tidy
    WHERE is_detected = 1 AND pesticide_name NOT IN ('NO DETECTION', 'NO DATA')
    GROUP BY "كود العينة"
    HAVING COUNT(*) >= 10
)
"""
print("Query 4 (>= 10 detections):", con.execute(query4).fetchone()[0])

# 5. Check the specific samples where count is exactly 10
query5 = """
SELECT "كود العينة", "اسم العينة", COUNT(*) as c
FROM chemistry_tidy
WHERE is_detected = 1 AND pesticide_name NOT IN ('NO DETECTION', 'NO DATA')
GROUP BY "كود العينة", "اسم العينة"
HAVING COUNT(*) = 10
"""
df = con.execute(query5).df()
print("\nSamples with exactly 10 detections (count: {}):".format(len(df)))
print(df)

con.close()
