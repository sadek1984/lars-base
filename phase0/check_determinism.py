"""
check_determinism.py
=====================
Detects answers that change between runs. Every question in questions_bank.csv
is answered and fingerprinted (hash of the reply text + hash of the result
table, row order included). Two kinds of variation are checked:

  seeds  — the full bank in a fresh process per PYTHONHASHSEED value
           (catches set/dict ordering and anything else that differs per
           process, e.g. DuckDB GROUP BY output order without ORDER BY)
  orders — the full bank twice in ONE engine instance, forward then
           reversed (catches state leaking from one question to the next)

Usage:
    python check_determinism.py                 # seeds 1 2 3 + both orders
    python check_determinism.py --seeds 1 2 3 4 5
    python check_determinism.py --worker SEED ORDER   (internal)

Exit code 0 when every question gives identical fingerprints, 1 otherwise.
"""
import argparse
import contextlib
import csv
import hashlib
import io
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LARS = HERE.parent / "src" / "LARS"
DB_PATH = LARS / "data" / "lars_data_demo.duckdb"
BANK = HERE / "questions_bank.csv"


def _fingerprint(text, df):
    """text-hash:table-hash:sorted-table-hash. The third part ignores row order,
    so a mismatch only in the second part means 'same rows, different order'."""
    h = lambda s: hashlib.sha1(s.encode()).hexdigest()[:12]
    th = h(text or "")
    if df is None:
        return f"{th}:none:none"
    rows = df.astype(str).to_csv(index=False).splitlines()
    return f"{th}:{h(chr(10).join(rows))}:{h(chr(10).join(rows[:1] + sorted(rows[1:])))}"


def worker(order: str) -> None:
    """Answer the bank in `order` ('forward', 'reverse', or 'both' = forward
    then reverse in the same engine) and print {id: fingerprint} JSON."""
    sys.path.insert(0, str(LARS))
    logging.disable(logging.CRITICAL)
    with contextlib.redirect_stdout(io.StringIO()):
        from modules.query.core_query_engine import CoreQueryEngine
        engine = CoreQueryEngine(db_path=str(DB_PATH))
    with BANK.open(encoding="utf-8") as f:
        bank = [(r["id"], r["question"]) for r in csv.DictReader(f)]
    passes = {"forward": [bank], "reverse": [bank[::-1]], "both": [bank, bank[::-1]]}[order]
    out = {}
    for i, qs in enumerate(passes):
        for qid, q in qs:
            with contextlib.redirect_stdout(io.StringIO()):
                text, df = engine.process(q)[:2]
            out[f"{qid}#{i}"] = _fingerprint(text, df)
    print(json.dumps(out))


def run(seed: str, order: str) -> dict:
    env = dict(os.environ, PYTHONHASHSEED=seed)
    proc = subprocess.run([sys.executable, __file__, "--worker", seed, order],
                          env=env, capture_output=True, text=True, check=True)
    return json.loads(proc.stdout.strip().splitlines()[-1])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", nargs="+", default=["1", "2", "3"])
    ap.add_argument("--worker", nargs=2, metavar=("SEED", "ORDER"))
    args = ap.parse_args()
    if args.worker:
        worker(args.worker[1])
        return 0

    varying = {}
    # Seeds: one forward pass per fresh process.
    seed_runs = {s: run(s, "forward") for s in args.seeds}
    for key in seed_runs[args.seeds[0]]:
        prints = {s: r[key] for s, r in seed_runs.items()}
        if len(set(prints.values())) > 1:
            varying.setdefault(key.split("#")[0], []).append(f"seeds {prints}")
    # Orders: forward then reverse in one engine instance.
    both = run(args.seeds[0], "both")
    for key, fp in both.items():
        qid, i = key.split("#")
        if i == "0" and both.get(f"{qid}#1") != fp:
            varying.setdefault(qid, []).append(f"order forward={fp} reverse={both[qid + '#1']}")

    total = len(seed_runs[args.seeds[0]])
    print(f"Questions checked: {total} | seeds: {' '.join(args.seeds)} | orders: forward, reverse")
    print(f"Varying: {len(varying)}")
    for qid in sorted(varying):
        for line in varying[qid]:
            print(f"  {qid}: {line}")
    return 1 if varying else 0


if __name__ == "__main__":
    sys.exit(main())
