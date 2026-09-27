"""
Semantic layer evaluation.

  (a) failure set:  python phase0/semantic_eval.py failure  [--out ...]
      phase0/semantic_failure_set.csv (19 questions x 4 variants) through the
      full engine in LIVE mode. Expected answers from independent SQL; each
      answer graded CORRECT / ALT / REFUSAL / WRONG.
        CORRECT  the numbers/names the question asks for
        ALT      a defensible, clearly labeled different metric (e.g. EU MRL
                 instead of the official verdict for a vague "الوضع")
        REFUSAL  an honest refusal (no numbers)
        WRONG    numbers that do not answer the question
  (b) bank:         python phase0/semantic_eval.py bank [--out ...]
      Every bank question through the semantic path only (handlers bypassed),
      compared with the handler answer.

Writes to logs/semantic_eval_log.jsonl (not the production log).
"""
import argparse
import csv
import json
import logging
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LARS = REPO / "src" / "LARS"
DB = LARS / "data" / "lars_data_demo.duckdb"
sys.path.insert(0, str(LARS))
os.environ.setdefault("LARS_SEMANTIC_LOG", str(REPO / "logs" / "semantic_eval_log.jsonl"))

import duckdb  # noqa: E402

CODE = '"كود العينة"'
NC = "sample_result = 'Non-Compliant'"


# ── independent expectations ─────────────────────────────────────────────────

class Expect:
    def __init__(self, con):
        self.con = con
        with (LARS / "config" / "analyte_map.csv").open(encoding="utf-8") as f:
            self.amap = {r["raw_name"]: r["canonical_name"] for r in csv.DictReader(f)}
        self.max_date = con.execute("SELECT MAX(test_date) FROM chemistry_tidy").fetchone()[0]

    def q(self, sql, params=()):
        return self.con.execute(sql, list(params)).fetchall()

    def detected(self, where, canonical=True):
        out = defaultdict(set)
        above = defaultdict(set)
        for raw, code, ab in self.q(f"""SELECT pesticide_name, {CODE}, is_above_limit FROM chemistry_tidy
                WHERE is_detected = 1 AND pesticide_name NOT IN ('NO DETECTION','NO DATA') AND {where}"""):
            name = self.amap.get(raw) if canonical else raw.lower()   # handlers fold case only
            if name:
                out[name].add(code)
                if ab == 1:
                    above[name].add(code)
        return out, above

    def top(self, where, n, canonical=True, by_above=False):
        det, ab = self.detected(where, canonical)
        key = (lambda p: (-len(ab[p]), -len(det[p]), p)) if by_above else (lambda p: (-len(det[p]), p))
        return [(p, len(det[p])) for p in sorted(det, key=key)[:n]]

    def count(self, where):
        return self.q(f"SELECT COUNT(DISTINCT {CODE}) FROM chemistry_tidy WHERE {where}")[0][0]


def build_expected(e: Expect):
    two_months = f"test_date >= DATE '{e.max_date}' - INTERVAL 2 month"
    one_month = f"test_date >= DATE '{e.max_date}' - INTERVAL 1 month"
    hood_nc = e.q(f"""SELECT "الحى", COUNT(DISTINCT {CODE}) n, COUNT(DISTINCT CASE WHEN {NC} THEN {CODE} END) k
        FROM chemistry_tidy WHERE "الحى" IS NOT NULL AND "الحى" != '' GROUP BY 1""")
    months = e.q(f"""SELECT strftime(test_date, '%Y-%m'), COUNT(DISTINCT {CODE}),
            COUNT(DISTINCT CASE WHEN {NC} THEN {CODE} END),
            COUNT(DISTINCT CASE WHEN is_above_limit = 1 THEN {CODE} END)
        FROM chemistry_tidy WHERE test_date IS NOT NULL GROUP BY 1 ORDER BY 1""")
    nuts_products = {p for (p,) in e.q(f"""SELECT DISTINCT "اسم العينة" FROM chemistry_tidy
        WHERE "نوع العينة" = 'Nuts' AND is_detected = 1""")}
    return {
        "F01": {"list": {p: len(s) for p, s in e.detected(""""نوع العينة" = 'Nuts'""")[0].items()}},
        "F02": {"list": {p: len(s) for p, s in e.detected(""""نوع العينة" = 'Vegetables'""")[0].items()}},
        "F03": {"nc": {"all": e.count(f""""نوع العينة" = 'Nuts' AND {NC}""")}},
        "F04": {"nc": {"all": e.count(f""""نوع العينة" = 'Fruits' AND "اسم البلدية" = 'بلدية الديرة الفرعية' AND {NC}""")}},
        "F05": {"top": e.top(""""نوع العينة" = 'Vegetables'""", 5)},
        "F06": {"top": e.top(f"{NC} AND {two_months}", 8),
                "top_handler": e.top(f"{NC} AND {two_months}", 8, canonical=False, by_above=True)},
        "F07": {"months": months},
        "F08": {"samples": e.count(one_month), "nc_value": e.count(f"{one_month} AND {NC}")},
        "F09": {"samples": e.count("test_date BETWEEN DATE '2026-01-01' AND DATE '2026-03-31'")},
        "F10": {"hoods_rate": [h for h, n, k in sorted((x for x in hood_nc if x[1] >= 10),
                                                      key=lambda x: (-round(100 * x[2] / x[1], 1), x[0]))[:3]],
                "hoods_count": [h for h, n, k in sorted(hood_nc, key=lambda x: (-x[2], x[0]))[:3]]},
        "F11": {"samples": e.count("strftime(test_date, '%Y-%m') = '2026-03'")},
        "A025": {"products": nuts_products},
        "A038": {"top": e.top(""""نوع العينة" = 'Spices'""", 10)},
        "A039": {"top": e.top(""""نوع العينة" = 'Vegetables'""", 5)},
        "A040": {"never": sorted(set(e.detected("TRUE")[0]) - set(e.detected(""""نوع العينة" = 'Fruits'""")[0]))},
        "B019": {"above_samples": e.count(""""نوع العينة" = 'Spices' AND limit_value > 0 AND concentration / limit_value >= 2""")},
        "B023": {"nc_by_cat": {"Vegetables": e.count(f""""نوع العينة" = 'Vegetables' AND {NC}"""),
                               "Fruits": e.count(f""""نوع العينة" = 'Fruits' AND {NC}""")}},
        "B049": {"rates": (round(100 * e.count(f""""نوع العينة" = 'Spices' AND {NC}""") / e.count(""""نوع العينة" = 'Spices'"""), 1),
                           round(100 * e.count(NC) / e.count("TRUE"), 1))},
        "D023": {"share": round(100 * e.count(f""""نوع العينة" = 'Spices' AND {NC}""") / e.count(NC), 1)},
    }


# ── grading ──────────────────────────────────────────────────────────────────

def is_refusal(text, df):
    return df is None or (hasattr(df, "empty") and df.empty and str(text).lstrip().startswith("⚠"))


def col(df, *names):
    for n in names:
        if df is not None and n in df.columns:
            return n
    return None


def body(df, group):
    return df[df[group] != "الإجمالي"] if group and group in df.columns else df


def grade(base, exp, text, df):
    if is_refusal(text, df):
        return "REFUSAL", ""
    ex = exp[base]
    pest = col(df, "pesticide")
    if "list" in ex:
        if pest and col(df, "samples_detected"):
            got = dict(zip(df[pest], df["samples_detected"]))
            return ("CORRECT", "") if got == ex["list"] else ("WRONG", f"{len(got)} vs {len(ex['list'])} analytes")
        return "WRONG", f"no pesticide list: {list(df.columns)}"
    if "top" in ex:
        if not pest:
            return "WRONG", f"no ranking: {list(df.columns)}"
        got = list(zip(df[pest], df["samples_detected"]))
        n = len(ex["top"])
        if got[:n] == ex["top"]:
            return "CORRECT", "" if len(got) == n else f"listed {len(got)}, first {n} match"
        if "top_handler" in ex and got == ex["top_handler"]:
            return "CORRECT", "handler definition (above-limit first, spellings not merged)"
        return "WRONG", f"got {[p for p, _ in got[:n]]}"
    if "nc" in ex:
        c = col(df, "non_compliant")
        if c and len(df) and int(body(df, col(df, "category", "municipality", "product")).iloc[-1][c] if False else df[c].iloc[-1]) == ex["nc"]["all"]:
            return "CORRECT", ""
        return "WRONG", f"expected {ex['nc']['all']} non-compliant; got {df.iloc[-1].to_dict() if len(df) else 'empty'}"
    if "months" in ex:
        m = col(df, "month", "period")
        if m == "period" and col(df, "violating_samples"):          # handler D019 shape (EU MRL)
            got = list(zip(df[m], df["sample_count"], df["violating_samples"]))
            ok = got == [(mo, n, a) for mo, n, k, a in ex["months"]]
            return ("ALT", "EU MRL per month (labeled), handler") if ok else ("WRONG", "monthly numbers differ")
        if not m:
            return "WRONG", f"not monthly: {list(df.columns)}"
        rows = body(df, m)
        official = [(mo, n, k) for mo, n, k, a in ex["months"]]
        technical = [(mo, n, a) for mo, n, k, a in ex["months"]]
        if col(rows, "non_compliant") and list(zip(rows[m], rows["samples"], rows["non_compliant"])) == official:
            return "CORRECT", "official verdict per month"
        if col(rows, "above_limit_samples") and list(zip(rows[m], rows["samples"], rows["above_limit_samples"])) == technical:
            return "ALT", "EU MRL per month (labeled)"
        if list(zip(rows[m], rows["samples"])) == [(mo, n) for mo, n, *_ in ex["months"]]:
            return "ALT", "sample counts per month only"
        return "WRONG", "monthly numbers differ"
    if "samples" in ex:
        s = col(df, "samples", "total_samples", "unique_samples", "sample_count")
        if s and int(df[s].iloc[-1]) == ex["samples"]:
            return "CORRECT", ""
        return "WRONG", f"expected {ex['samples']} samples; got {df.iloc[-1].to_dict() if len(df) else 'empty'}"
    if "hoods_rate" in ex:
        h = col(df, "neighborhood")
        if not h:
            return "WRONG", f"not by neighborhood: {list(df.columns)}"
        got = list(body(df, h)[h])[:3]
        rate_col = col(df, "rate_pct")
        if col(df, "non_compliant") and got in (ex["hoods_rate"], ex["hoods_count"]) and (
                "غير المطابقة" in text):
            return "CORRECT", "official " + ("rate" if got == ex["hoods_rate"] and rate_col else "count")
        if "above_limit_samples" in df.columns:
            return "ALT", "EU MRL ranking (labeled)"
        return "WRONG", f"got {got}"
    if "products" in ex:
        p = col(df, "product")
        if p and set(body(df, p)[p]) == ex["products"]:
            return "CORRECT", ""
        return "WRONG", "answers a different question (not which nut products)"
    if "never" in ex:
        return ("CORRECT", "") if pest and list(df[pest]) == ex["never"] else ("WRONG", "never-detected list differs")
    if "above_samples" in ex:
        c = col(df, "above_limit_samples")
        return ("CORRECT", "") if c and int(df[c].iloc[-1]) == ex["above_samples"] else ("WRONG", "count differs")
    if "nc_by_cat" in ex:
        c, g = col(df, "non_compliant"), col(df, "category")
        if c and g and all(int(df[df[g] == k][c].iloc[0]) == v for k, v in ex["nc_by_cat"].items() if (df[g] == k).any()) \
                and set(ex["nc_by_cat"]) <= set(df[g]):
            return "CORRECT", ""
        return "WRONG", "category counts differ or missing"
    if "rates" in ex:
        r = col(df, "rate_pct")
        vals = set(df[r]) if r else set()
        spices, overall = ex["rates"]
        if r and spices in vals and overall in vals and "غير المطابقة" in text:
            return "CORRECT", ""
        return "WRONG", f"expected {spices}% and {overall}%; got {sorted(vals)}"
    if "share" in ex:
        g = col(df, "category")
        if g and "share_pct" in df.columns and (df[g] == "Spices").any() and \
                float(df[df[g] == "Spices"]["share_pct"].iloc[0]) == ex["share"] and col(df, "non_compliant"):
            return "CORRECT", ""
        return "WRONG", f"expected share {ex['share']}%"
    return "WRONG", "no grader"


# ── runs ─────────────────────────────────────────────────────────────────────

def last_spec(log_path, question):
    try:
        lines = Path(log_path).read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return None
    for line in reversed(lines):
        r = json.loads(line)
        if r["question"] == question:
            return r.get("spec"), (r.get("validation") or {}).get("message"), (r.get("llm") or {}).get("error")
    return None


def run_failure(out_path):
    os.environ["LARS_SEMANTIC_MODE"] = "live"
    logging.disable(logging.CRITICAL)
    from modules.query.core_query_engine import CoreQueryEngine
    engine = CoreQueryEngine(db_path=str(DB))
    assert engine.semantic_mode == "live", "semantic layer did not start"
    with duckdb.connect(str(DB), read_only=True) as con:
        exp = build_expected(Expect(con))
    rows = list(csv.DictReader((REPO / "phase0" / "semantic_failure_set.csv").open(encoding="utf-8")))
    results = []
    for r in rows:
        text, df = engine.process(r["question"])[:2]
        source = engine.last_source
        verdict, note = grade(r["base"], exp, text, df)
        spec = last_spec(os.environ["LARS_SEMANTIC_LOG"], r["question"]) if source == "semantic" or engine._refusal else None
        results.append({**r, "source": source, "handler_refusal": engine._refusal or "",
                        "verdict": verdict, "note": note,
                        "spec": json.dumps(spec[0], ensure_ascii=False) if spec and spec[0] else "",
                        "semantic_error": (spec[1] or spec[2] or "") if spec and not source == "semantic" else "",
                        "answer_head": str(text).split("\n")[0][:300]})
        print(f"{r['id']:6} {source:8} {verdict:8} {note[:70]}")
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0]))
        w.writeheader()
        w.writerows(results)
    print(Counter(x["verdict"] for x in results))
    print(f"→ {out_path}")


_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _numbers(text, df):
    nums = {x.replace(",", "") for x in _NUM.findall(str(text))}
    if df is not None:
        for v in df.select_dtypes("number").to_numpy().ravel():
            if v == v:
                nums.add(f"{v:g}")
                nums.add(str(int(v)) if float(v).is_integer() else f"{v:.1f}")
    return nums


def _names(text, df):
    blob = str(text).lower()
    if df is not None:
        blob += " " + " ".join(str(x).lower() for x in df.astype(str).to_numpy().ravel())
    return blob


def agreement(ans, h_text, h_df):
    """Heuristic: the semantic answer's key values appear in the handler answer."""
    df = ans.df
    key_names = next((c for c in ("pesticide", "product", "category", "municipality", "neighborhood", "month")
                      if c in df.columns), None)
    if key_names in ("pesticide", "product") or "samples_detected" in df.columns:
        names = [str(x).lower() for x in df[key_names] if x != "الإجمالي"][:10]
        blob = _names(h_text, h_df)
        hit = sum(n in blob for n in names)
        return hit >= max(1, round(0.8 * len(names))), f"{hit}/{len(names)} names in handler answer"
    main = [c for c in ("rate_pct", "non_compliant", "above_limit_samples", "samples") if c in df.columns][:1]
    vals = [f"{v:g}" if not float(v).is_integer() else str(int(v)) for v in df[main[0]]] if main else []
    got = _numbers(h_text, h_df)
    hit = sum(v in got for v in vals)
    return hit == len(vals) and bool(vals), f"{hit}/{len(vals)} values in handler answer"


def run_bank(out_path):
    """Semantic path only, for every bank question; compared with handlers."""
    os.environ["LARS_SEMANTIC_MODE"] = "off"
    logging.disable(logging.CRITICAL)
    from modules.query.core_query_engine import CoreQueryEngine
    from modules.semantic.fallback import SemanticFallback
    engine = CoreQueryEngine(db_path=str(DB))
    sem = SemanticFallback(str(DB), "live")
    bank = list(csv.DictReader((REPO / "phase0" / "questions_bank.csv").open(encoding="utf-8")))
    results = []
    for r in bank:
        h_text, h_df = engine.process(r["question"])[:2]
        refusal = engine._refusal or ""
        ans = sem.answer(r["question"], h_text, refusal or "bank-eval", serve=False, use_cache=False)
        rec = last_spec(sem.log_path, r["question"])
        h_ok = not is_refusal(h_text, h_df)
        agree, why = agreement(ans, h_text, h_df) if (ans and h_ok) else (None, "")
        results.append({
            "id": r["id"], "question": r["question"], "handler_refusal": refusal,
            "handler_answered": not is_refusal(h_text, h_df),
            "semantic_answered": ans is not None,
            "spec": json.dumps(rec[0], ensure_ascii=False) if rec and rec[0] else "",
            "semantic_message": "" if ans else (rec[1] or rec[2] or "") if rec else "",
            "handler_head": str(h_text).split("\n")[0][:200],
            "semantic_head": ans.text.split("\n")[0][:300] if ans else "",
            "semantic_result": ans.text.split("\n")[1][:200] if ans and "\n" in ans.text else "",
            "agree": "" if agree is None else ("yes" if agree else "NO"), "note": why,
        })
        print(r["id"], results[-1]["handler_answered"], results[-1]["semantic_answered"], results[-1]["spec"][:100])
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0]))
        w.writeheader()
        w.writerows(results)
    both = [x for x in results if x["handler_answered"] and x["semantic_answered"]]
    print(f"both answered {len(both)}; agree {sum(x['agree'] == 'yes' for x in both)}; "
          f"handler only {sum(x['handler_answered'] and not x['semantic_answered'] for x in results)}; "
          f"semantic only {sum(x['semantic_answered'] and not x['handler_answered'] for x in results)}")
    print(f"→ {out_path}")


def run_stability(out_path, runs=3):
    """Fill the spec `runs` times (no cache) for every question the semantic
    layer would see; list questions whose validated spec differs → UNSTABLE."""
    os.environ["LARS_SEMANTIC_MODE"] = "off"
    logging.disable(logging.CRITICAL)
    from modules.query.core_query_engine import CoreQueryEngine
    from modules.semantic.fallback import SEMANTIC_ELIGIBLE, SemanticFallback
    engine = CoreQueryEngine(db_path=str(DB))
    sem = SemanticFallback(str(DB), "live")
    qs = [r["question"] for r in csv.DictReader((REPO / "phase0" / "semantic_failure_set.csv").open(encoding="utf-8"))]
    for r in csv.DictReader((REPO / "phase0" / "questions_bank.csv").open(encoding="utf-8")):
        engine.process(r["question"])
        if engine._refusal in SEMANTIC_ELIGIBLE:
            qs.append(r["question"])
    rows = []
    for q in dict.fromkeys(qs):
        specs = []
        for _ in range(runs):
            spec, llm = sem.fill_spec(q)
            specs.append(spec.model_dump_json(exclude_defaults=True) if spec else f"ERROR {llm.get('error', '')[:80]}")
        stable = len(set(specs)) == 1
        rows.append({"question": q, "stable": "yes" if stable else "UNSTABLE", **{f"run{i + 1}": x for i, x in enumerate(specs)}})
        print("   " if stable else "UNSTABLE", q)
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"{sum(r['stable'] != 'yes' for r in rows)} UNSTABLE of {len(rows)} → {out_path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("which", choices=["failure", "bank", "stability"])
    ap.add_argument("--out")
    a = ap.parse_args()
    out = a.out or str(REPO / "logs" / f"semantic_eval_{a.which}.csv")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    {"failure": run_failure, "bank": run_bank, "stability": run_stability}[a.which](out)
