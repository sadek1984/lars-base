"""
Warm the semantic cache of a running lars_service before a demo.

    python scripts/warmup_demo.py [--url http://localhost:8000] [--tries 3]

Each demo question is POSTed to /api/lars/query ({"query": ...}) up to
--tries times until it no longer needs the semantic layer, or the semantic
layer has answered it:
  source "semantic"               a validated spec was served, and is now cached
  source "handler", no refusal    the handlers answer it (nothing to cache)
  refusal "out_of_scope"          never goes to the semantic layer
Anything else (a refusal the semantic layer did not answer: LLM timeout,
"unsupported", spec rejected) is retried.

The cache lives in the service process's memory: it is lost on restart and
each uvicorn worker has its own, so warm a single-worker service after its
last restart. The service must run with LARS_SEMANTIC_MODE=live (the
default); /health reports the mode and the script stops otherwise.
"""
import argparse
import json
import sys
import time
import urllib.request

QUESTIONS = [
    "كم عينة غير مطابقة في المكسرات",
    "أكثر 5 مبيدات في الخضار",
    "شلون كان الوضع شهر بشهر",
    "من يناير إلى مارس 2026",
    "أعلى 5 أحياء في نسبة عدم المطابقة في آخر شهرين",
    "أخطر 5 أحياء من حيث نسبة المخالفة في آخر شهر",
    "نسبة الرسوب في التوابل مقارنة بالمعدل العام",
    "ملخص تنفيذي للربع الأول",
    "ملخص تنفيذي للربع الثاني",
    "أعلى 5 أحياء في نسبة عدم المطابقة",
    "نسبة عدم المطابقة في الكمون",
    "عدد العينات عدم المطابقة في مارس",
    "ما هي أعلى خمس مبيدات في آخر شهرين؟",
    "أعلى 5 مبيدات في الخضار",
    "أهم 10 مبيدات في التوابل",
]


def call(url: str, payload=None, timeout: float = 60.0) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"},
                                 method="GET" if data is None else "POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def settled(r: dict) -> bool:
    if not r.get("success"):
        return False
    return (r.get("source") == "semantic" or r.get("refusal") is None
            or r.get("refusal") == "out_of_scope")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--tries", type=int, default=3)
    a = ap.parse_args()
    base = a.url.rstrip("/")

    health = call(f"{base}/health")
    if health.get("semantic_mode") != "live":
        print(f"Service semantic_mode is {health.get('semantic_mode')!r}, not 'live' — nothing to warm.")
        return 2

    failed = 0
    for q in QUESTIONS:
        r, tries = {}, 0
        for tries in range(1, a.tries + 1):
            t0 = time.perf_counter()
            try:
                r = call(f"{base}/api/lars/query", {"query": q})
            except Exception as e:           # network error / timeout: retry
                r = {"success": False, "answer": f"{type(e).__name__}: {e}"}
            r["seconds"] = round(time.perf_counter() - t0, 1)
            if settled(r):
                break
        ok = settled(r)
        failed += not ok
        first = (r.get("answer") or "").strip().splitlines()[0] if r.get("answer") else ""
        status = "OK " if ok else "!! "
        print(f"{status}{q}\n    source={r.get('source')} refusal={r.get('refusal')} "
              f"tries={tries} last={r.get('seconds')}s\n    {first}")
    print(f"\n{len(QUESTIONS) - failed}/{len(QUESTIONS)} settled.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
