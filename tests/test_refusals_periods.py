"""
Typed refusals and period-blind handlers (voice-testing bugs, 2026-09-28).

1. Every refusal is a messages.Refusal carrying its kind, whichever code path
   built it; process() reads the kind from the answer (engine._refusal).
2. A period that was extracted may only be answered by a handler verified to
   filter by it (_PERIOD_VERIFIED) that actually received it; otherwise the
   typed period_not_applied refusal. Quarters are answered only by a
   quarterly breakdown; a named year only for one month of the data's year.

Run:  pytest tests/test_refusals_periods.py -v
"""
import csv
import logging
import pickle
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
LARS = REPO / "src" / "LARS"
DB_PATH = LARS / "data" / "lars_data_demo.duckdb"
sys.path.insert(0, str(LARS))

pytestmark = pytest.mark.skipif(not DB_PATH.exists(), reason="lars_data_demo.duckdb not present")

from modules.query.messages import (MULTI_MONTH_MESSAGE, PERIOD_NOT_APPLIED_MESSAGE,  # noqa: E402
                                    UNRESOLVED_PERIOD_MESSAGE, Refusal, refusal_kind)
from modules.query.text_norm import named_years, names_quarter  # noqa: E402
from modules.semantic import fallback as fb  # noqa: E402
from modules.semantic.llm import SpecProvider  # noqa: E402

HOODS = "ما هي أخطر 5 أحياء من حيث نسبة المخالفة في {}"


@pytest.fixture(scope="module")
def engine():
    logging.disable(logging.CRITICAL)
    from modules.query.core_query_engine import CoreQueryEngine
    e = CoreQueryEngine(db_path=str(DB_PATH))
    e.semantic_mode, e._semantic = "off", None
    return e


@pytest.fixture(scope="module")
def bank():
    with (REPO / "phase0" / "questions_bank.csv").open(encoding="utf-8") as f:
        return {r["id"]: r["question"] for r in csv.DictReader(f)}


# ── Refusal type ─────────────────────────────────────────────────────────────

def test_refusal_is_its_text():
    r = Refusal("multi_month", "⚠️ x")
    assert r == "⚠️ x" and str(r) == "⚠️ x" and refusal_kind(r) == "multi_month"
    assert refusal_kind("⚠️ x") is None and refusal_kind(None) is None
    # the period label appended at the end of _process_unguarded keeps the kind
    assert refusal_kind(r + "\n\n📅 label") == "multi_month"
    assert refusal_kind(pickle.loads(pickle.dumps(r))) == "multi_month"


# ── 1. every refusal kind is classified ──────────────────────────────────────

@pytest.mark.parametrize("q, kind", [
    ("من يناير إلى مارس 2026", "multi_month"),
    ("كم عدد العينات من يناير إلى مارس 2026؟", "multi_month"),
    ("كم عدد العينات من يناير إلى مارس", "multi_month"),
    ("في مارس 2026", "not_understood"),
    ("ما سعر الطماطم؟", "not_understood"),
    ("الربع الأول 2026", "unresolved_period"),
    ("كم عدد العينات في مارس 2025", "unresolved_period"),      # month filter would ignore the year
    ("كم عدد العينات في 2026", "unresolved_period"),
    ("ما عدد عينات الطماطم الراسبة خلال الأشهر الأخيرة؟", "unresolved_period"),
    ("ما هي المبيدات في عينات الثوم؟", "unresolved_product"),
    ("ما هي المبيدات في بلدية القمر؟", "unresolved_municipality"),   # built in keyword_patterns
    ("كم عدد العينات غير المطابقة في المكسرات؟", "category"),
    (HOODS.format("آخر شهرين"), "period_not_applied"),
    (HOODS.format("آخر شهر"), "period_not_applied"),
    (HOODS.format("آخر 3 أيام"), "period_not_applied"),
    ("ما هو ملخص تنفيذي للربع الأول؟", "period_not_applied"),
    ("أولوية التفتيش في آخر شهر", "period_not_applied"),
])
def test_refusal_kind_from_any_path(engine, q, kind):
    text, df = engine.process(q)[:2]
    assert engine._refusal == kind and refusal_kind(text) == kind and df is None
    assert kind in fb.SEMANTIC_ELIGIBLE


def test_out_of_scope_is_typed_and_not_eligible(engine, bank):
    text = engine.process(bank["C016"])[0]
    assert refusal_kind(text) == engine._refusal == "out_of_scope"
    assert "out_of_scope" not in fb.SEMANTIC_ELIGIBLE


def test_refusal_texts_unchanged():
    assert MULTI_MONTH_MESSAGE == "⚠️ الفترات التي تشمل أكثر من شهر غير مدعومة حالياً."
    assert UNRESOLVED_PERIOD_MESSAGE.startswith("⚠️ لم أتمكن من فهم الفترة الزمنية")


# ── 2. period-blind handlers ─────────────────────────────────────────────────

@pytest.mark.parametrize("q", [HOODS.format("آخر شهرين"), HOODS.format("آخر شهر"), HOODS.format("آخر 3 أيام")])
def test_period_blind_ranking_is_refused(engine, q):
    text, df = engine.process(q)[:2]
    assert text == PERIOD_NOT_APPLIED_MESSAGE and df is None
    assert [c[0] for c in engine._handlers_called] == ["_handle_top_n_by_metric"]


def test_same_ranking_without_period_still_answered(engine):
    text, df = engine.process("ما هي أخطر 5 أحياء من حيث نسبة المخالفة")[:2]
    assert engine._refusal is None and df is not None and len(df) == 5


@pytest.mark.parametrize("q, n", [
    ("كم عدد العينات في مارس 2026", 266),                # month of the data's only year
    ("كم عدد المخالفات في شهرين الأخيرين؟", None),
    ("ما عدد عينات الطماطم الراسبة آخر ٣ شهور؟", None),
])
def test_period_applying_handlers_answer(engine, q, n):
    text, df = engine.process(q)[:2]
    assert engine._refusal is None and engine._period_applied(engine._extract_context(q)["detected_period"])
    if n is not None:
        assert f"{n}" in text


def test_quarterly_breakdown_still_answers_quarters(engine, bank):
    text, df = engine.process(bank["D016"])[:2]        # بين الربع الأول والربع الثاني
    assert engine._refusal is None and list(df["period"]) == ["2026-Q1", "2026-Q2"]


def test_period_verified_handlers_take_the_period(engine):
    import inspect
    for name in engine._PERIOD_VERIFIED:
        params = inspect.signature(getattr(type(engine), name)).parameters
        assert "date_filter" in params or "ctx" in params, name


def test_period_applied_requires_the_same_filter(engine):
    f = engine._extract_context("آخر شهر")["detected_period"]
    engine._handlers_called = [("_handle_list_pesticides", (["Tomato"],), {"date_filter": f})]
    assert engine._period_applied(f)
    engine._handlers_called = [("_handle_list_pesticides", (["Tomato"],), {})]
    assert not engine._period_applied(f)                 # verified handler, period not passed
    engine._handlers_called = [("_handle_top_n_by_metric", ("neighborhood",), {})]
    assert not engine._period_applied(f)                 # not on the list
    engine._handlers_called = []
    assert not engine._period_applied(f)


def test_names_period(engine):
    assert engine.names_period(HOODS.format("آخر شهر")) and engine.names_period("الربع الأول")
    assert not engine.names_period("ما هي أخطر 5 أحياء من حيث نسبة المخالفة")


@pytest.mark.parametrize("q, quarter, years", [
    ("الربع الأول 2026", True, [2026]), ("ملخص تنفيذي للربع الأول", True, []),
    ("ربع العينات", False, []), ("Q2 2026", True, [2026]),
    ("في مارس ٢٠٢٦", False, [2026]), ("العينة 2031", False, []), ("العينة ١٧٥٠", False, []),
])
def test_quarter_and_year_detection(q, quarter, years):
    assert names_quarter(q) is quarter and named_years(q) == years


# ── live: the refusal goes to the semantic layer ─────────────────────────────

class PartialSpec(SpecProvider):
    """What Gemini returned for these questions: metric + group_by only."""
    name = "fake"

    def fill(self, question, system_prompt):
        return '{"metric": "noncompliance_rate", "group_by": "neighborhood"}'


@pytest.fixture
def live(engine, tmp_path):
    engine.semantic_mode = "live"
    engine._semantic = fb.SemanticFallback(str(DB_PATH), "live", provider=PartialSpec(),
                                           log_path=tmp_path / "log.jsonl")
    yield engine
    engine.semantic_mode, engine._semantic = "off", None


@pytest.mark.parametrize("window, rows", [
    # independent SQL: official verdict, >= 10 samples per neighborhood, anchored on MAX(test_date)
    ("آخر شهرين", [("الصباخ", 15, 4), ("ربيشة", 17, 4), ("الفلاح", 15, 3), ("الأخضر", 50, 9), ("القادسية", 30, 5)]),
    ("آخر شهر", [("الصباخ", 15, 4), ("الفلاح", 15, 3), ("النهضة", 10, 2), ("الأخضر", 50, 9), ("القادسية", 30, 5)]),
    ("آخر 3 أيام", [("الجردة", 32, 2)]),
])
def test_live_semantic_answers_the_window(live, window, rows):
    text, df = live.process(HOODS.format(window))[:2]
    assert live.last_source == "semantic" and live._refusal == "period_not_applied"
    got = [(r.neighborhood, r.samples, r.non_compliant) for r in df.iloc[:-1].itertuples()]
    assert got == rows
    if len(rows) < 5:
        assert "عدد الأحياء التي لديها 10 عينات أو أكثر ضمن هذه الشروط: 1 فقط (المطلوب 5)" in text


def test_semantic_says_when_no_group_reaches_the_threshold():
    import duckdb
    from modules.query.entity_resolver import EntityResolver
    from modules.semantic.answer import answer_spec
    from modules.semantic.catalog import build_catalog
    from modules.semantic.query_spec import QuerySpec
    cat = build_catalog(str(DB_PATH))
    with duckdb.connect(str(DB_PATH), read_only=True) as con:
        res = EntityResolver(con)
    spec = QuerySpec.model_validate({"metric": "noncompliance_rate", "group_by": "neighborhood",
                                     "filters": {"product": ["طماطم"]},
                                     "period": {"type": "relative", "n": 3, "unit": "day"}})
    a = answer_spec(spec, cat, res, str(DB_PATH))      # 1 tomato sample in the window
    assert a.ok and "لا يوجد أي حي بعدد 10 عينات أو أكثر ضمن هذه الشروط" in a.text
    assert list(a.df["neighborhood"]) == ["الإجمالي"]


@pytest.mark.parametrize("q, period, ok", [
    ("كم عدد العينات في مارس 2025", {"type": "absolute_month", "month": 3}, False),   # year dropped → 2026
    ("كم عدد العينات في مارس 2026", {"type": "absolute_month", "month": 3}, True),
    ("كم عدد العينات من يناير إلى مارس 2026", {"type": "range", "from_month": 1, "to_month": 3, "end": "2026-03-31"}, True),
    ("كم عدد العينات في 2026", None, False),
])
def test_semantic_keeps_the_named_year(q, period, ok):
    import duckdb
    from modules.query.entity_resolver import EntityResolver
    from modules.semantic.answer import answer_spec
    from modules.semantic.catalog import build_catalog
    from modules.semantic.query_spec import QuerySpec
    cat = build_catalog(str(DB_PATH))
    with duckdb.connect(str(DB_PATH), read_only=True) as con:
        res = EntityResolver(con)
    spec = QuerySpec.model_validate({"metric": "sample_count", **({"period": period} if period else {})})
    a = answer_spec(spec, cat, res, str(DB_PATH), question=q)
    assert a.ok is ok, a.text


# ── partial periods: the data ends 2026-05-17 ────────────────────────────────

PARTIAL = "البيانات المتاحة حتى 17 مايو 2026"


@pytest.mark.parametrize("period, note, nc, n", [
    ({"type": "range", "from_month": 4, "to_month": 6, "year": 2026}, "(الربع غير مكتمل)", 89, 744),   # Q2
    ({"type": "absolute_month", "month": 5}, "(الشهر غير مكتمل)", 30, 229),
    ({"type": "latest_month"}, "(الشهر غير مكتمل)", 30, 229),
    ({"type": "range", "from_month": 3, "to_month": 5}, "(الفترة غير مكتملة)", None, None),
    ({"type": "range", "from_month": 1, "to_month": 3, "year": 2026}, None, 152, 1111),                # Q1: complete
    ({"type": "relative", "n": 2, "unit": "month"}, None, None, None),                                   # anchored on MAX
])
def test_semantic_says_the_period_is_incomplete(period, note, nc, n):
    import duckdb
    from modules.query.entity_resolver import EntityResolver
    from modules.semantic.answer import answer_spec
    from modules.semantic.catalog import build_catalog
    from modules.semantic.query_spec import QuerySpec
    cat = build_catalog(str(DB_PATH))
    with duckdb.connect(str(DB_PATH), read_only=True) as con:
        res = EntityResolver(con)
    a = answer_spec(QuerySpec.model_validate({"metric": "noncompliance_rate", "period": period}), cat, res, str(DB_PATH))
    lines = a.text.splitlines()
    assert a.ok and lines[0].startswith("فهمت سؤالك كالتالي")
    if note:
        assert lines[1] == f"{PARTIAL} {note}"
    else:
        assert PARTIAL not in a.text
    if n is not None:
        assert (int(a.df["non_compliant"].iloc[0]), int(a.df["samples"].iloc[0])) == (nc, n)


def test_handler_month_says_it_is_incomplete(engine):
    may = engine.process("ما هي العينات غير المطابقة في شهر مايو؟")[0]
    march = engine.process("ما هي العينات غير المطابقة في شهر مارس؟")[0]
    assert may.endswith(f"⚠️ {PARTIAL} (الشهر غير مكتمل)") and PARTIAL not in march


# ── "عدم المطابقة" = non-compliance (text_norm.canonical_compliance) ──────────

@pytest.mark.parametrize("q", ["نسبة عدم المطابقة", "عدم مطابقة الكمون", "عدم التطابق", "حالات عدم الامتثال",
                               "عدم الإمتثال", "وعدم المطابقة", "عدم مطابقتها للمواصفات", "نسبة عَدَمِ المُطابَقَة"])
def test_adam_is_non_compliant(q):
    from modules.query.text_norm import compliance_intent, norm
    assert compliance_intent(q) == "non_compliant" and "غير" in norm(q) and "عدم" not in norm(q)


def test_adam_elsewhere_untouched():
    from modules.query.text_norm import canonical_compliance, compliance_intent
    q = "كم عدد المتبقيات التي تعذّر تقييمها لعدم وجود حد؟"          # B033
    assert canonical_compliance(q) == q and compliance_intent(q) is None
    assert compliance_intent("نسبة المطابقة") == "compliant"


def test_engine_sees_adam_as_non_compliant(engine):
    ctx = engine._extract_context("عدد العينات عدم المطابقة في مارس")
    assert "غير المطابقة" in str(ctx["query"])                       # raw text too (router, regexes)


@pytest.mark.parametrize("q, samples, nc", [
    ("نسبة عدم المطابقة في الكمون", 233, 147),        # SQL: Cumin + Ground Cumin + Cumin Seeds
    ("عدد العينات عدم المطابقة في مارس", 266, 24),
])
def test_adam_answers_match_sql(engine, q, samples, nc):
    text = engine.process(q)[0]
    assert engine._refusal is None and "Non-Compliant samples" in text
    assert f"**{samples}**" in text and f"Non-Compliant: {nc}**" in text


# ── shape guard: a ranking/breakdown by a group must be grouped by it ────────

@pytest.mark.parametrize("q, dim", [
    ("أعلى 5 أحياء في نسبة عدم المطابقة", "neighborhood"), ("ما هي أخطر ٥ أحياء من حيث نسبة المخالفة؟", "neighborhood"),
    ("الأحياء الأكثر مخالفة", "neighborhood"), ("لكل بلدية", "municipality"), ("ما عدد العينات في كل بلدية", "municipality"),
    ("أعلى ٥ منتجات من حيث نسبة الرسوب", "product"), ("شلون كان الوضع شهر بشهر", "month"),
    ("ما عدد العينات المفحوصة شهرياً؟", "month"), ("حسب الشهر", "month"),
    ("كم عينة في حي الإسكان", None), ("آخر 3 أشهر", None), ("كم عدد الأحياء", None), ("أكثر 5 مبيدات", None),
])
def test_requested_grouping(q, dim):
    from modules.query.text_norm import requested_grouping
    assert requested_grouping(q) == dim


@pytest.mark.parametrize("qid, dim", [("C010", "المنتج"), ("D031", "الشهر")])
def test_wrong_shape_is_refused(engine, bank, qid, dim):
    text, df = engine.process(bank[qid])[:2]
    assert engine._refusal == "group_not_applied" and df is None and f"موزعة حسب {dim}" in text


@pytest.mark.parametrize("qid", ["A055", "B029", "B041", "D007", "D010", "D011", "D015", "D030", "E012"])
def test_right_shape_still_answers(engine, bank, qid):
    _, df = engine.process(bank[qid])[:2]
    assert engine._refusal is None and df is not None and len(df)


@pytest.mark.parametrize("q", ["أعلى 5 أحياء في نسبة عدم المطابقة", "أعلى 5 أحياء في نسبة عدم المطابقة في آخر شهرين"])
def test_neighborhood_ranking_goes_to_semantic(live, q):
    text, df = live.process(q)[:2]
    assert live._refusal == "group_not_applied" and live.last_source == "semantic"
    assert list(df["neighborhood"])[-1] == "الإجمالي" and len(df) == 6         # top 5 + total
    if "شهرين" not in q:   # SQL, all data: العجيبة 21/40, خب القبر 4/11, البساتين 14/57, ربيشة 4/17, الصباخ 11/49
        assert [(r.neighborhood, r.samples, r.non_compliant) for r in df.iloc[:-1].itertuples()] == [
            ("العجيبة", 40, 21), ("خب القبر", 11, 4), ("البساتين", 57, 14), ("ربيشة", 17, 4), ("الصباخ", 49, 11)]
