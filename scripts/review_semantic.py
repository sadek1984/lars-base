"""
Turn logs/semantic_log.jsonl into a CSV for manual grading.

    python scripts/review_semantic.py [--log logs/semantic_log.jsonl] [--out semantic_review.csv]
                                      [--mode live|shadow] [--served-only]

One row per semantic run, with an empty "correct?" column to fill in.
"""
import argparse
import csv
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

COLUMNS = ["timestamp", "mode", "question", "handler_refusal", "handler_text", "spec", "validation_ok",
           "validation_message", "row_count", "answer", "served", "cache_hit", "llm_error",
           "llm_latency_ms", "latency_ms", "sql", "correct?", "notes"]


def rows(log: Path, mode=None, served_only=False):
    with log.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            if (mode and r.get("mode") != mode) or (served_only and not r.get("served")):
                continue
            llm = r.get("llm") or {}
            yield {
                "timestamp": r.get("timestamp"), "mode": r.get("mode"), "question": r.get("question"),
                "handler_refusal": (r.get("handler") or {}).get("refusal"),
                "handler_text": (r.get("handler") or {}).get("text"),
                "spec": json.dumps(r.get("spec"), ensure_ascii=False) if r.get("spec") else "",
                "validation_ok": (r.get("validation") or {}).get("ok"),
                "validation_message": (r.get("validation") or {}).get("message"),
                "row_count": r.get("row_count"), "answer": r.get("answer"), "served": r.get("served"),
                "cache_hit": llm.get("cache_hit"), "llm_error": llm.get("error"),
                "llm_latency_ms": llm.get("latency_ms"), "latency_ms": r.get("latency_ms"),
                "sql": r.get("sql"), "correct?": "", "notes": "",
            }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", default=str(REPO / "logs" / "semantic_log.jsonl"))
    ap.add_argument("--out", default=str(REPO / "logs" / "semantic_review.csv"))
    ap.add_argument("--mode", choices=["live", "shadow"])
    ap.add_argument("--served-only", action="store_true")
    a = ap.parse_args()
    out = list(rows(Path(a.log), a.mode, a.served_only))
    with open(a.out, "w", newline="", encoding="utf-8-sig") as f:   # BOM: Excel shows Arabic
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(out)
    print(f"{len(out)} runs → {a.out}")


if __name__ == "__main__":
    main()
