"""
Deterministic semantic specs (modules/semantic/rules.py), the pesticide
dimension of the shape guard, and the voice-test questions of 2026-09-28.

Run:  pytest tests/test_semantic_rules.py -v
"""
import json
import logging
import sys
from pathlib import Path

import duckdb
import pytest

REPO = Path(__file__).resolve().parents[1]
LARS = REPO / "src" / "LARS"
DB_PATH = LARS / "data" / "lars_data_demo.duckdb"
sys.path.insert(0, str(LARS))

pytestmark = pytest.mark.skipif(not DB_PATH.exists(), reason="lars_data_demo.duckdb not present")

from modules.semantic import fallback as fb  # noqa: E402
from modules.semantic.llm import SpecProvider  # noqa: E402
from modules.semantic.rules import rule_spec  # noqa: E402

HOODS_Q = "أعلى 5 أحياء غير مطابقة في آخر شهرين"
HOODS_PARAPHRASES = ["أكثر 5 أحياء فيها عينات غير مطابقة في آخر شهرين",
                     "أخطر خمسة أحياء من حيث المخالفات خلال الشهرين الماضيين"]
TWO_MONTHS = "test_date >= DATE '2026-05-17' - INTERVAL 2 month"


def spec_of(q):
    s = rule_spec(q)
    return None if s is None else (s.metric.value, s.group_by.value, s.top_n if "top_n" in s.model_fields_set else None,
                                   s.period.model_dump(mode="json", exclude_defaults=True) if s.period.type.value != "none" else None)


# ── rule_spec ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("q, expected", [
    (HOODS_Q, ("noncompliant_count", "neighborhood", 5, {"type": "relative", "n": 2, "unit": "month"})),
    (HOODS_PARAPHRASES[0], ("noncompliant_count", "neighborhood", 5, {"type": "relative", "n": 2, "unit": "month"})),
    (HOODS_PARAPHRASES[1], ("noncompliant_count", "neighborhood", 5, {"type": "relative", "n": 2, "unit": "month"})),
    ("ما هي أعلى 5 أحياء في نسبة عدم المطابقة", ("noncompliance_rate", "neighborhood", 5, None)),
    ("أعلى 3 بلديات مخالفة في مارس", ("noncompliant_count", "municipality", 3, {"type": "absolute_month", "month": 3})),
    ("أسوأ 4 منتجات رسوب هذا الشهر", ("noncompliant_count", "product", 4, {"type": "latest_month"})),
    ("أكثر الأحياء غير مطابقة", ("noncompliant_count", "neighborhood", None, None)),
])
def test_rule_matches(q, expected):
    assert spec_of(q) == expected


@pytest.mark.parametrize("q", [
    "أعلى 5 أحياء غير مطابقة في الطماطم",        # a product: not clean → LLM
    "أعلى 5 أحياء غير مطابقة في 2026",           # a year
    "أعلى 5 أحياء غير مطابقة في الربع الأول",    # a quarter
    "أعلى 5 أحياء غير مطابقة من يناير إلى مارس",  # two months
    "أعلى 5 أحياء",                              # no violation word
    "أعلى 5 مبيدات غير مطابقة",                  # not a group of places/products
    "أعلى 5 أحياء غير مطابقة في بلدية الرس",      # a municipality filter
])
def test_rule_falls_back_to_the_llm(q):
    assert rule_spec(q) is None


# ── live: the rule answers, the LLM is not called ────────────────────────────

class Unsupported(SpecProvider):
    """What Gemini did for these questions: the right spec, unsupported=true."""
    name = "fake"

    def __init__(self):
        self.calls = []

    def fill(self, question, system_prompt):
        self.calls.append(question)
        return ('{"metric": "noncompliant_count", "group_by": "neighborhood", "top_n": 5, '
                '"unsupported": true, "reason": "x"}')


@pytest.fixture(scope="module")
def engine():
    logging.disable(logging.CRITICAL)
    from modules.query.core_query_engine import CoreQueryEngine
    e = CoreQueryEngine(db_path=str(DB_PATH))
    e.semantic_mode, e._semantic = "off", None
    return e


@pytest.fixture
def live(engine, tmp_path):
    provider = Unsupported()
    engine.semantic_mode = "live"
    engine._semantic = fb.SemanticFallback(str(DB_PATH), "live", provider=provider, log_path=tmp_path / "log.jsonl")
    yield engine, provider, tmp_path / "log.jsonl"
    engine.semantic_mode, engine._semantic = "off", None


def expected_hoods(n=5):
    """SQL: official verdict, distinct samples per neighborhood, last 2 months."""
    with duckdb.connect(str(DB_PATH), read_only=True) as c:
        rows = c.execute(f"""WITH s AS (SELECT "الحى" h, "كود العينة" k,
                MAX(CASE WHEN sample_result = 'Non-Compliant' THEN 1 ELSE 0 END) nc
            FROM chemistry_tidy WHERE {TWO_MONTHS} AND "الحى" IS NOT NULL AND "الحى" != '' GROUP BY 1, 2)
            SELECT h, COUNT(*) n, SUM(nc) k FROM s GROUP BY h ORDER BY k DESC, h""").fetchall()
    top = rows[:n]
    tied = [h for h, _, k in rows[n:] if k == top[-1][2]]
    return top, tied


@pytest.mark.parametrize("q", [HOODS_Q] + HOODS_PARAPHRASES)
def test_neighborhood_ranking_by_rule_matches_sql(live, q):
    engine, provider, log = live
    text, df = engine.process(q)[:2]
    top, tied = expected_hoods()
    assert engine.last_source == "semantic" and provider.calls == []            # no LLM call
    assert [(r.neighborhood, r.samples, r.non_compliant) for r in df.iloc[:-1].itertuples()] == top
    assert tuple(df.iloc[-1][["neighborhood", "samples", "non_compliant"]]) == ("الإجمالي", 835, 99)
    assert "عدد العينات غير المطابقة (حسب النتيجة الرسمية للمختبر)" in text
    assert f"{top[0][2]} عينة غير مطابقة من أصل {top[0][1]}" in text           # count next to total samples
    assert tied == ["الفايزية"] and "بنفس قيمة المرتبة 5 أيضاً: الفايزية" in text
    rec = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
    assert rec["source"] == "semantic-rule" and rec["llm"]["provider"] == "semantic-rule" and rec["served"]


def test_unmatched_question_still_uses_the_llm(live):
    engine, provider, _ = live
    engine.process("أعلى 5 أحياء غير مطابقة في الربع الأول")
    assert provider.calls                                                        # rule declined → LLM


# ── pesticides: ranking routes and the shape guard ──────────────────────────

PEST_TWO_MONTHS = ["ما هي أعلى 5 مبيدات في آخر شهرين؟", "أكثر خمس مبيدات ظهوراً في آخر شهرين",
                   "أبرز 5 مبيدات خلال الشهرين الماضيين"]
PEST_NC = ["ما هي أعلى 5 مبيدات من حيث العينات غير المطابقة؟", "أكثر 5 مبيدات في العينات غير المطابقة",
           "أهم خمس مبيدات في العينات الراسبة"]


@pytest.fixture(scope="module")
def con():
    from modules.query.mappings import PESTICIDE_VARIANTS
    c = duckdb.connect(str(DB_PATH), read_only=True)
    c.execute("CREATE TEMP TABLE variants(v VARCHAR, canon VARCHAR)")
    c.executemany("INSERT INTO variants VALUES (?, ?)",
                  [(v.lower(), k) for k, vs in PESTICIDE_VARIANTS.items() for v in vs])
    yield c
    c.close()


def top_pesticides(con, where, order):
    return con.execute(f"""
        SELECT COALESCE(v.canon, lower(t.pesticide_name)) AS pesticide,
               COUNT(DISTINCT t."كود العينة") AS det,
               COUNT(DISTINCT CASE WHEN t.is_above_limit = 1 THEN t."كود العينة" END) AS above
        FROM chemistry_tidy t LEFT JOIN variants v ON lower(t.pesticide_name) = v.v
        WHERE {where} AND t.is_detected = 1 AND t.pesticide_name NOT IN ('NO DETECTION', 'NO DATA')
        GROUP BY 1 ORDER BY {order}, pesticide LIMIT 5""").fetchall()


def rows(df):
    return list(df[["pesticide", "samples_detected", "samples_above_limit"]].itertuples(index=False, name=None))


@pytest.mark.parametrize("q", PEST_TWO_MONTHS)
def test_top_pesticides_in_two_months(engine, con, q):
    text, df = engine.process(q)[:2]
    assert [c[0] for c in engine._handlers_called] == ["_handle_top_pesticides"] and engine._refusal is None
    assert ": 835 عينة" in text.splitlines()[0]
    assert rows(df) == top_pesticides(con, TWO_MONTHS.replace("test_date", 't.test_date'), "det DESC, above DESC")


@pytest.mark.parametrize("q", PEST_NC)
def test_top_pesticides_in_non_compliant_samples(engine, con, q):
    text, df = engine.process(q)[:2]
    assert [c[0] for c in engine._handlers_called] == ["_handle_top_pesticides"] and engine._refusal is None
    assert ": 240 عينة" in text.splitlines()[0]
    assert rows(df) == top_pesticides(con, "t.sample_result = 'Non-Compliant'", "above DESC, det DESC")


@pytest.mark.parametrize("q, dim", [
    ("ما هي أعلى 5 مبيدات من حيث العينات غير المطابقة؟", "pesticide"), ("أكثر ١٠ مبيدات تكراراً", "pesticide"),
    ("المبيدات الأكثر ظهوراً", "pesticide"), ("ما نسبة المخالفة لكل مبيد على حده؟", "pesticide"),
    ("ما هي العينات التي تحتوي على أكثر من ٥ مبيدات؟", None), ("ما هو توزيع عدد المبيدات في الخيار؟", None),
    ("ما هي المبيدات في آخر 3 أشهر المبيدات", None),
])
def test_pesticide_grouping(q, dim):
    from modules.query.text_norm import requested_grouping
    assert requested_grouping(q) == dim


def test_pesticide_ranking_answered_by_products_is_refused(engine, monkeypatch):
    """The voice bug: a pesticide ranking answered with a per-PRODUCT table."""
    import pandas as pd
    table = pd.DataFrame({"sample_type": ["Cumin"], "sample_count": [1], "non_compliant": [1], "compliant": [0]})
    monkeypatch.setattr(engine, "_dispatch_top_pesticides", lambda ctx: None)
    monkeypatch.setattr(engine, "_handle_count_samples_compliance_table",
                        lambda *a, **k: (engine._handlers_called.append(("_handle_count_samples_compliance_table", a, k))
                                         or ("table", table)))
    text, df = engine.process("ما هي أعلى 5 مبيدات من حيث العينات غير المطابقة؟")[:2]
    assert engine._refusal == "group_not_applied" and df is None and "موزعة حسب المبيد" in text


def test_per_pesticide_stats_in_the_text_count_as_grouped(engine, bank_e010="ما هي min و max و mean و median لكل مبيد في الطماطم؟"):
    text, df = engine.process(bank_e010)[:2]
    assert engine._refusal is None and "Detected Pesticide Statistics" in text
