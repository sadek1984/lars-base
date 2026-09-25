#!/usr/bin/env python3
"""
LARS consistency test (metamorphic testing).

Idea: a paraphrase of a question must return the SAME data as the original.
We compare result fingerprints (the DataFrame / numbers), not answer wording.

Two stages, so you can review the paraphrases before running them:

  1) generate  -> paraphrases.csv   (LLM writes variants; YOU skim/edit the file)
  2) run       -> consistency_results.csv + review_queue.csv + summary per axis

Usage:
  export ANTHROPIC_API_KEY=...
  python consistency_test.py generate --bank questions_bank.csv --out paraphrases.csv
  python consistency_test.py run --paraphrases paraphrases.csv \
      --db /Users/a12/lars-base/src/LARS/data/lars_data_test_copy.duckdb

Adjust --engine-import / --sys-path if the refactor moved CoreQueryEngine.
"""

import argparse
import csv
import hashlib
import importlib
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict

# ─────────────────────────────────────────────────────────────────────────────
# Variation axes — each paraphrase is tagged with one, so failures are diagnosable
# ─────────────────────────────────────────────────────────────────────────────
AXES = {
    "saudi_dialect": "Najdi/Qassimi Saudi dialect as a municipal official would speak it "
                     "(وش، كم، عطني، ابغى، هالسنة).",
    "spontaneous":   "Spontaneous spoken style: a false start or self-correction, filler words "
                     "(يعني، طيب)، slightly messy word order.",
    "spoken_numbers": "Any numbers, months or periods written as spoken words "
                      "(e.g. 'ثلاثة' not '3', 'شهر واحد' not '1'). Keep them ABSOLUTE — "
                      "never turn a named month into 'last month'.",
    "asr_noise":     "Simulate speech-recognition errors: misspell pesticide/product names the "
                     "way an ASR might hear them (e.g. كلوربيريفوس -> كلور بيري فوس), drop or "
                     "swap a hamza, merge or split a word.",
    "msa_formal":    "Formal Modern Standard Arabic, different sentence structure from the original.",
}

GEN_PROMPT = """You rewrite Arabic questions for testing a food-safety lab query system.
The system answers from a pesticide-residue database (samples, products, pesticides,
neighborhoods, municipalities, compliance status, test dates).

Original question:
{question}

Write exactly ONE paraphrase for EACH style below. HARD RULES:
- Keep the meaning identical: same product, pesticide, neighborhood, time period,
  compliance filter, and same kind of answer (count vs list vs ranking vs percentage).
- Do not add or drop any filter. Do not make the question more or less specific.
- Keep dates/months absolute exactly as in the original.

Styles:
{axes}

Return ONLY a JSON array, no prose, no markdown fences:
[{{"axis": "<style key>", "text": "<paraphrase>"}}, ...]"""


# ─────────────────────────────────────────────────────────────────────────────
# Stage 1: generate
# ─────────────────────────────────────────────────────────────────────────────
def read_bank(path, id_col, q_col, only_ids=None):
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        sys.exit(f"Empty bank: {path}")
    if id_col not in rows[0] or q_col not in rows[0]:
        sys.exit(f"Columns not found. Available: {list(rows[0].keys())} "
                 f"(use --id-col / --q-col)")
    out = [(r[id_col].strip(), r[q_col].strip()) for r in rows if r[q_col].strip()]
    if only_ids:
        wanted = set(only_ids)
        out = [x for x in out if x[0] in wanted]
    return out


def call_llm(client, model, question, axes):
    axes_txt = "\n".join(f"- {k}: {v}" for k, v in axes.items())
    msg = client.messages.create(
        model=model,
        max_tokens=1500,
        messages=[{"role": "user",
                   "content": GEN_PROMPT.format(question=question, axes=axes_txt)}],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    text = re.sub(r"```(?:json)?|```", "", text).strip()
    items = json.loads(text)
    return [(i["axis"], i["text"].strip()) for i in items
            if i.get("axis") in axes and i.get("text", "").strip()]


def cmd_generate(a):
    try:
        import anthropic
    except ImportError:
        sys.exit("pip install anthropic")
    client = anthropic.Anthropic()
    axes = {k: v for k, v in AXES.items() if not a.axes or k in a.axes}
    bank = read_bank(a.bank, a.id_col, a.q_col, a.ids)

    done = set()
    if os.path.exists(a.out) and not a.overwrite:           # resume support
        with open(a.out, newline="", encoding="utf-8") as f:
            done = {r["qid"] for r in csv.DictReader(f)}
    mode = "a" if done else "w"

    with open(a.out, mode, newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if mode == "w":
            w.writerow(["qid", "axis", "original", "variant", "keep"])
        for n, (qid, q) in enumerate(bank, 1):
            if qid in done:
                continue
            for attempt in range(3):
                try:
                    variants = call_llm(client, a.model, q, axes)
                    break
                except Exception as e:                        # bad JSON / rate limit
                    print(f"  {qid} attempt {attempt+1} failed: {e}")
                    time.sleep(2 * (attempt + 1))
            else:
                print(f"  {qid} skipped")
                continue
            for axis, v in variants:
                w.writerow([qid, axis, q, v, "1"])
            f.flush()
            print(f"[{n}/{len(bank)}] {qid}: {len(variants)} variants")

    print(f"\nWrote {a.out}. Skim it now: set keep=0 on any variant that changed the "
          f"meaning, before running.")


# ─────────────────────────────────────────────────────────────────────────────
# Stage 2: run + compare
# ─────────────────────────────────────────────────────────────────────────────
NUM_RE = re.compile(r"\d+(?:[.,]\d+)?")
AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩٫", "0123456789.")


def df_fingerprint(df, decimals=4):
    """Order-independent hash of a DataFrame's content."""
    import pandas as pd
    d = df.copy()
    d = d.reindex(sorted(d.columns, key=str), axis=1)
    for c in d.columns:
        if pd.api.types.is_float_dtype(d[c]):
            d[c] = d[c].round(decimals)
    rows = sorted("|".join(map(str, r)) for r in d.astype(str).itertuples(index=False))
    payload = ";".join(map(str, d.columns)) + "\n" + "\n".join(rows)
    return hashlib.md5(payload.encode("utf-8")).hexdigest()[:12]


def text_numbers(text):
    return sorted(NUM_RE.findall((text or "").translate(AR_DIGITS)))


def understood(engine, q, handlers_called):
    """What the engine made of the question: handler chain + resolved entities.
    Read-only introspection; empty if the engine does not expose these hooks."""
    ents = {}
    try:
        ctx = engine._extract_context(q)
        for k in ("detected_samples", "detected_neighborhoods", "detected_pesticide",
                  "category_key", "detected_period_label"):
            if ctx.get(k):
                ents[k.replace("detected_", "")] = ctx[k]
        res = ctx.get("resolution")
        for k in ("municipalities", "facilities", "pesticide_group", "product_terms_unresolved"):
            if res is not None and getattr(res, k, None):
                ents[k] = getattr(res, k)
    except Exception:
        pass
    return " > ".join(dict.fromkeys(handlers_called)), json.dumps(ents, ensure_ascii=False)


def run_one(engine, q, unknown_markers, error_markers=(), refusal_markers=()):
    """Returns dict(status, fp, nrows, text, handler, entities)."""
    calls = getattr(engine, "_ct_calls", None)
    if calls is not None:
        calls.clear()
    try:
        text, df = engine.process(q)[:2]
    except Exception as e:
        return {"status": "ERROR", "fp": "", "nrows": -1, "text": f"{type(e).__name__}: {e}",
                "handler": "", "entities": ""}
    text = text or ""
    handler, entities = understood(engine, q, list(calls or []))
    base = {"text": text, "handler": handler, "entities": entities}
    # Order matters: an error or refusal reply may also contain generic wording.
    if any(m in text for m in error_markers):
        return {**base, "status": "ERROR", "fp": "", "nrows": 0}
    if any(m in text for m in refusal_markers):
        return {**base, "status": "REFUSAL", "fp": "", "nrows": 0}
    if any(m in text for m in unknown_markers):
        return {**base, "status": "UNANSWERED", "fp": "", "nrows": 0}
    if df is not None and hasattr(df, "columns"):
        return {**base, "status": "OK", "fp": "df:" + df_fingerprint(df), "nrows": len(df)}
    # No table: fall back to the numbers mentioned in the text answer
    nums = text_numbers(text)
    fp = "num:" + hashlib.md5(",".join(nums).encode()).hexdigest()[:12]
    return {**base, "status": "OK", "fp": fp, "nrows": 0}


def classify(orig, var):
    if orig["status"] != "OK":
        return "SKIP_ORIG_" + orig["status"]
    if var["status"] == "ERROR":
        return "ERROR"
    if var["status"] == "UNANSWERED":
        return "UNANSWERED"          # safe failure: honest "I don't understand" / "not found"
    if var["status"] == "REFUSAL":
        return "REFUSAL"             # out-of-scope refusal for an answerable question
    if var["fp"] == orig["fp"]:
        return "WEAK_MATCH" if orig["nrows"] == 0 and orig["fp"].startswith("df:") else "MATCH"
    return "MISMATCH"                # answered, but different data -> review first


def load_engine(a):
    for p in a.sys_path:
        sys.path.insert(0, p)
    mod_name, cls_name = a.engine_import.split(":")
    cls = getattr(importlib.import_module(mod_name), cls_name)
    engine = cls(db_path=a.db, enable_llm_fallback=a.llm_fallback)
    # Record which handlers answer each question (test-only instance wrappers).
    engine._ct_calls = []
    for name in dir(engine):
        if name.startswith("_handle_") and callable(getattr(engine, name, None)):
            fn = getattr(engine, name)
            def wrapped(*args, _fn=fn, _name=name, **kw):
                engine._ct_calls.append(_name)
                return _fn(*args, **kw)
            setattr(engine, name, wrapped)
    return engine


def cmd_run(a):
    with open(a.paraphrases, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r.get("keep", "1").strip() != "0"]
    if a.ids:
        rows = [r for r in rows if r["qid"] in set(a.ids)]
    print(f"{len(rows)} variants to run. Loading engine...")
    engine = load_engine(a)
    markers = a.unknown_markers
    kw = {"error_markers": a.error_markers, "refusal_markers": a.refusal_markers}

    originals = {}
    for r in rows:                                   # run each original once
        if r["qid"] not in originals:
            originals[r["qid"]] = run_one(engine, r["original"], markers, **kw)

    results = []
    for n, r in enumerate(rows, 1):
        t0 = time.perf_counter()
        v = run_one(engine, r["variant"], markers, **kw)
        ms = int((time.perf_counter() - t0) * 1000)
        o = originals[r["qid"]]
        verdict = classify(o, v)
        results.append({
            "qid": r["qid"], "axis": r["axis"], "verdict": verdict,
            "original": r["original"], "variant": r["variant"],
            "orig_rows": o["nrows"], "var_rows": v["nrows"], "var_ms": ms,
            "orig_handler": o["handler"], "var_handler": v["handler"],
            "orig_entities": o["entities"], "var_entities": v["entities"],
            "orig_answer": o["text"][:300].replace("\n", " "),
            "var_answer": v["text"][:300].replace("\n", " "),
        })
        if n % 25 == 0:
            print(f"  ...{n}/{len(rows)}")

    fields = list(results[0].keys()) if results else []
    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(results)
    review = [x for x in results if x["verdict"] in ("MISMATCH", "ERROR")]
    with open(a.review, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(review)

    # ── Summary ──
    scored = [x for x in results if not x["verdict"].startswith("SKIP")]
    c = Counter(x["verdict"] for x in results)
    print("\n=== Overall ===")
    for k in ("MATCH", "WEAK_MATCH", "UNANSWERED", "REFUSAL", "MISMATCH", "ERROR"):
        print(f"  {k:<11} {c.get(k, 0)}")
    skipped = sum(v for k, v in c.items() if k.startswith("SKIP"))
    if skipped:
        print(f"  (skipped {skipped}: original itself unanswered/errored)")
    if scored:
        strict = c.get("MATCH", 0) / len(scored)
        safe = (c.get("MATCH", 0) + c.get("WEAK_MATCH", 0) + c.get("UNANSWERED", 0)
                + c.get("REFUSAL", 0)) / len(scored)
        print(f"\n  Consistency (strict MATCH):         {strict:.0%}")
        print(f"  Safe rate (no confident mismatch):  {safe:.0%}")

    print("\n=== Per axis ===  (share of scored variants)")
    by_axis = defaultdict(Counter)
    for x in scored:
        by_axis[x["axis"]][x["verdict"]] += 1
    for axis, cc in sorted(by_axis.items()):
        tot = sum(cc.values())
        print(f"  {axis:<15} n={tot:<4} match {(cc['MATCH'] + cc['WEAK_MATCH'])/tot:>4.0%}   "
              f"unans {cc['UNANSWERED']/tot:>4.0%}   refusal {cc['REFUSAL']/tot:>4.0%}   "
              f"MISMATCH {cc['MISMATCH']/tot:>4.0%}   error {cc['ERROR']/tot:>4.0%}")

    slow = sorted(results, key=lambda x: -x["var_ms"])[:5]
    print("\n=== Slowest variants (engine only, no ASR/TTS) ===")
    for x in slow:
        print(f"  {x['var_ms']:>6} ms  {x['qid']}  {x['variant'][:60]}")

    print(f"\nFull results: {a.out}\nReview first: {a.review}  ({len(review)} rows)")


# ─────────────────────────────────────────────────────────────────────────────
def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate")
    g.add_argument("--bank", default="questions_bank.csv")
    g.add_argument("--out", default="paraphrases.csv")
    g.add_argument("--id-col", default="id")
    g.add_argument("--q-col", default="question")
    g.add_argument("--ids", nargs="*", help="only these question IDs")
    g.add_argument("--axes", nargs="*", choices=list(AXES), help="subset of axes")
    g.add_argument("--model", default=os.getenv("PARAPHRASE_MODEL", "claude-sonnet-5"))
    g.add_argument("--overwrite", action="store_true")
    g.set_defaults(func=cmd_generate)

    r = sub.add_parser("run")
    r.add_argument("--paraphrases", default="paraphrases.csv")
    r.add_argument("--db", required=True)
    r.add_argument("--engine-import", default="modules.query.core_query_engine:CoreQueryEngine")
    r.add_argument("--sys-path", nargs="*", default=[
        "/Users/a12/lars-base/src/LARS", "/Users/a12/lars-base/src/LARS/modules"])
    r.add_argument("--llm-fallback", action="store_true",
                   help="enable Tier 3 LLM fallback (default off = deterministic only)")
    r.add_argument("--unknown-markers", nargs="*", default=[
        "couldn't fully understand", "لم أفهم", "لم استطع فهم", "لم أتمكن من فهم"],
        help="substrings of honest 'not understood' / 'not found in data' replies -> UNANSWERED")
    r.add_argument("--error-markers", nargs="*", default=[
        "حدث خطأ أثناء معالجة سؤالك", "تعذّر حساب النسبة"],
        help="substrings of the engine's polite error / rate-guard replies -> ERROR")
    r.add_argument("--refusal-markers", nargs="*", default=[
        "لا يمكنني اقتراح توصيات", "لا تحتوي قاعدة البيانات", "يحتاج إلى تعريف منهجية",
        "يجمع عدة أجزاء"],
        help="substrings of out-of-scope refusals -> REFUSAL (reported on its own line)")
    r.add_argument("--ids", nargs="*")
    r.add_argument("--out", default="consistency_results.csv")
    r.add_argument("--review", default="review_queue.csv")
    r.set_defaults(func=cmd_run)

    a = p.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()