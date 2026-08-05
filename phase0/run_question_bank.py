"""
run_question_bank.py
=====================
Phase 0 baseline harness. Pushes every question in questions_bank.csv through
the live CoreQueryEngine and records, per question:

    id, question, status, tier_hit, handler, generated_sql_present,
    row_count, latency_ms, error, answer_preview

This produces baseline.csv — the file every later phase gets diffed against.
No production code is touched. This only reads.

--------------------------------------------------------------------------
ADJUST BEFORE RUNNING — three things are environment-specific:

1. DB_PATH / import path below, to match your actual lars-base layout.
2. `call_engine()` — your core_query_engine.process() return shape.
   From your session history it returns something like:
       response_text, df = engine.process(question)
   or, for handler-routed answers:
       (text, df, meta) tuple
   This script tries both shapes defensively (see call_engine()) and
   records what it can find. If neither shape matches, fix call_engine()
   to match your actual signature — do not guess silently past that point.
3. `infer_tier()` — reads get_trust_badge()-style signals from meta / the
   response text if your engine exposes them (e.g. generated_sql is None
   => Tier 0/1 deterministic; generated_sql present => Tier 2/3 LLM path).
   Adjust the field names to whatever your CoreQueryEngine actually sets.
--------------------------------------------------------------------------

Usage:
    python run_question_bank.py questions_bank.csv baseline.csv
"""

import csv
import importlib
import sys
import time
import traceback
from pathlib import Path

# --- 1. ADJUST: point this at your actual lars-base engine import ---------
# Example matching your repo layout from prior sessions:
#   /Users/a12/lars-base/src/LARS/core_query_engine.py
sys.path.insert(0, "/Users/a12/lars-base/src/LARS")  # <-- change if needed

DB_PATH = "/Users/a12/lars-base/src/LARS/data/lars_data.duckdb"  # <-- change if needed


def get_engine():
    """
    Import and construct CoreQueryEngine exactly as your app does.
    Adjust the module/class name and constructor args to match your repo.
    """
    from modules.core_query_engine import CoreQueryEngine  # matches src/LARS/modules/, mirrors the app's own 'from modules...' internal imports
    engine = CoreQueryEngine(db_path=DB_PATH)                    # <-- confirm this kwarg name
    return engine


def call_engine(engine, question: str):
    """
    Calls engine.process(question) and normalizes whatever shape comes back
    into (response_text, df, meta_dict). Handles the 2-tuple and 3-tuple
    forms seen in your prior sessions. Raises on genuinely unexpected shapes
    so you notice instead of silently mis-recording results.
    """
    result = engine.process(question)

    if isinstance(result, tuple):
        if len(result) == 3:
            text, df, meta = result
        elif len(result) == 2:
            text, df = result
            meta = {}
        else:
            raise ValueError(f"engine.process() returned a {len(result)}-tuple; "
                              f"expected 2 or 3. Adjust call_engine().")
    else:
        # Some handler paths might return a single QueryResult-like object.
        # ADJUST: pull .text/.df/.meta (or whatever your object exposes).
        text = getattr(result, "text", None) or getattr(result, "answer", str(result))
        df = getattr(result, "df", None)
        meta = getattr(result, "meta", {}) or {}

    return text, df, meta


def infer_tier(meta: dict, text: str) -> str:
    """
    Best-effort tier classification for the baseline record.
    ADJUST field names to whatever your engine actually sets in meta.
    Falls back to a text heuristic on your existing trust-badge emoji
    convention (✅ Verified query vs 🤖 AI-generated) if meta is empty.
    """
    if meta:
        if meta.get("generated_sql") not in (None, ""):
            return "tier2_3_llm"
        if meta.get("intent"):
            return "tier1_2_intent_or_pattern"
        if meta.get("tier"):
            return str(meta["tier"])
    if text:
        if "✅" in text or "Verified" in text:
            return "deterministic_or_pattern (heuristic)"
        if "🤖" in text or "AI-generated" in text:
            return "llm (heuristic)"
    return "unknown"


def main():
    if len(sys.argv) != 3:
        print("Usage: python run_question_bank.py <questions_bank.csv> <baseline.csv>")
        sys.exit(1)

    bank_path = Path(sys.argv[1])
    out_path = Path(sys.argv[2])

    if not bank_path.exists():
        print(f"ERROR: {bank_path} not found. Run extract_question_bank.py first.")
        sys.exit(1)

    with bank_path.open(encoding="utf-8") as f:
        questions = list(csv.DictReader(f))

    print(f"Loaded {len(questions)} questions. Initializing engine...")
    engine = get_engine()
    print("Engine ready. Running harness (this will take a while for 220 queries)...")

    fieldnames = [
        "id", "question", "status", "tier_hit", "handler",
        "generated_sql_present", "row_count", "latency_ms",
        "error", "answer_preview",
    ]

    results = []
    for i, row in enumerate(questions, 1):
        qid = row["id"]
        question = row["question"]
        t0 = time.perf_counter()
        record = {
            "id": qid, "question": question, "status": "ok",
            "tier_hit": "", "handler": "", "generated_sql_present": "",
            "row_count": "", "latency_ms": "", "error": "",
            "answer_preview": "",
        }
        try:
            text, df, meta = call_engine(engine, question)
            latency_ms = round((time.perf_counter() - t0) * 1000, 1)

            record["tier_hit"] = infer_tier(meta, text)
            record["handler"] = meta.get("handler", meta.get("intent", ""))
            record["generated_sql_present"] = bool(meta.get("generated_sql"))
            record["row_count"] = len(df) if df is not None else 0
            record["latency_ms"] = latency_ms
            record["answer_preview"] = (text or "")[:120].replace("\n", " ")

        except Exception as e:
            latency_ms = round((time.perf_counter() - t0) * 1000, 1)
            record["status"] = "exception"
            record["latency_ms"] = latency_ms
            record["error"] = f"{type(e).__name__}: {e}"
            # full traceback goes to stderr, not the CSV, to keep it readable
            print(f"[{qid}] EXCEPTION: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)

        results.append(record)
        if i % 20 == 0:
            print(f"  ...{i}/{len(questions)} done")

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    # --- summary ---
    n_ok = sum(1 for r in results if r["status"] == "ok")
    n_err = sum(1 for r in results if r["status"] == "exception")
    n_zero = sum(1 for r in results if r["status"] == "ok" and r["row_count"] in (0, "0"))
    print(f"\nDone. {out_path} written.")
    print(f"  ok: {n_ok}  exceptions: {n_err}  zero-row results: {n_zero}")
    if n_err:
        print("  Review stderr above for tracebacks on failing IDs.")


if __name__ == "__main__":
    main()
