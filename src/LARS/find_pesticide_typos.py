import duckdb
from difflib import get_close_matches

con = duckdb.connect('src/LARS/data/lars_data.duckdb', read_only=True)
names = [r[0] for r in con.execute("SELECT DISTINCT pesticide_name FROM chemistry_tidy WHERE pesticide_name IS NOT NULL").fetchall()]
con.close()

names = sorted([n for n in names if isinstance(n, str)])
seen = set()
typos = {}

for name in names:
    matches = get_close_matches(name, names, n=3, cutoff=0.85)
    for match in matches:
        if match != name and match not in seen:
            if name not in seen: # Pair found
                print(f"Potential typo: {name} <-> {match}")
                seen.add(match) 
