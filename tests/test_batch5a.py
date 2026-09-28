"""
Batch 5a — "top N pesticides" (overall / in non-compliant samples) and the
multi-month refusal.

Every expected ranking is recomputed here with independent SQL: filters
applied directly, spelling variants merged by joining the PESTICIDE_VARIANTS
table inside SQL, distinct samples counted per pesticide, ordered by the
scope's definition.

Run:  pytest tests/test_batch5a.py -v
"""
import csv
import logging
import sys
from pathlib import Path

import duckdb
import pytest

REPO = Path(__file__).resolve().parents[1]
LARS = REPO / "src" / "LARS"
DB_PATH = LARS / "data" / "lars_data_demo.duckdb"
BANK = REPO / "phase0" / "questions_bank.csv"
sys.path.insert(0, str(LARS))

pytestmark = pytest.mark.skipif(not DB_PATH.exists(), reason="lars_data_demo.duckdb not present")

DATE = """strptime("التاريخ", '%d/%m/%Y')"""
ANCHOR = f"(SELECT MAX({DATE}) FROM chemistry_tidy)"
CUMIN = "('Cumin','Cumin Seeds','Ground Cumin')"

# (question, scope, N, extra SQL filter) — scope 'nc' = official Non-Compliant
EXAMPLES = [
    ("ما هي أكثر خمس مبيدات ظهرت في العينات غير المطابقة؟", "nc", 5, "1=1"),
    ("أكثر ٨ مبيدات ظهوراً في العينات غير المطابقة في آخر شهرين", "nc", 8,
     f"{DATE} >= {ANCHOR} - INTERVAL 2 month"),
    ("أكثر 5 مبيدات ظهوراً في العينات غير المطابقة في آخر 3 شهور", "nc", 5,
     f"{DATE} >= {ANCHOR} - INTERVAL 3 month"),
    ("ما المبيدات التي سببت عدم المطابقة في الكمون؟", "nc", 5, f"\"اسم العينة\" IN {CUMIN}"),
    ("أكثر 3 مبيدات في العينات غير المطابقة في بلدية شرق بريدة", "nc", 3,
     "\"اسم البلدية\" = 'بلدية شرق بريدة'"),
    ("ترتيب المبيدات حسب التكرار", "all", 5, "1=1"),
]


# Category-level questions are not supported: they get the honest refusal.
CATEGORY_QUESTIONS = [
    "وش المبيدات اللي في العينات اللي ما طابقت في الخضروات؟",
    "ما هي المبيدات الأكثر ظهوراً في الخضروات؟",
    "ما هي المبيدات الأكثر ظهوراً في المكسرات؟",
    "أكثر 10 مبيدات ظهوراً في الفواكه في مارس",
    "ما هي أكثر ١٠ مبيدات تكراراً في التوابل؟",      # A038
    "ما هي أكثر ٥ مبيدات تكراراً في الخضراوات؟",     # A039
    "المبيدات الموجودة في المكسرات",
    "ما هي المبيدات في الخضروات؟",
    "ما هي المبيدات التي ظهرت في الفواكه؟",
    "وش المبيدات اللي في التوابل؟",
    "كم عدد العينات غير المطابقة في المكسرات؟",
]


@pytest.fixture(scope="module")
def con():
    from modules.query.mappings import PESTICIDE_VARIANTS
    c = duckdb.connect(str(DB_PATH), read_only=True)
    c.execute("CREATE TEMP TABLE variants(v VARCHAR, canon VARCHAR)")
    c.executemany("INSERT INTO variants VALUES (?, ?)",
                  [(v.lower(), k) for k, vs in PESTICIDE_VARIANTS.items() for v in vs])
    yield c
    c.close()


@pytest.fixture(scope="module")
def engine():
    logging.disable(logging.CRITICAL)
    from modules.query.core_query_engine import CoreQueryEngine
    return CoreQueryEngine(db_path=str(DB_PATH))


@pytest.fixture(scope="module")
def bank():
    with BANK.open(encoding="utf-8") as f:
        return {r["id"]: r["question"] for r in csv.DictReader(f)}


def expected(con, scope, n, where):
    """(scope_total, [(pesticide, samples_detected, samples_above_limit), ...])."""
    verdict = "AND sample_result = 'Non-Compliant'" if scope == "nc" else ""
    total = con.execute(f"""SELECT COUNT(DISTINCT "كود العينة") FROM chemistry_tidy
        WHERE {where} {verdict}""").fetchone()[0]
    order = ("det DESC, above DESC" if scope == "all" else "above DESC, det DESC") + ", pesticide"
    rows = con.execute(f"""
        SELECT COALESCE(v.canon, lower(t.pesticide_name)) AS pesticide,
               COUNT(DISTINCT t."كود العينة") AS det,
               COUNT(DISTINCT CASE WHEN t.is_above_limit = 1 THEN t."كود العينة" END) AS above
        FROM chemistry_tidy t LEFT JOIN variants v ON lower(t.pesticide_name) = v.v
        WHERE {where} {verdict} AND t.is_detected = 1
          AND t.pesticide_name NOT IN ('NO DETECTION', 'NO DATA')
        GROUP BY 1 ORDER BY {order} LIMIT {n}""").fetchall()
    return total, rows


# ── Engine vs independent SQL ────────────────────────────────────────────────

@pytest.mark.parametrize("q, scope, n, where", EXAMPLES, ids=[e[0][:40] for e in EXAMPLES])
def test_ranking_matches_independent_sql(engine, con, q, scope, n, where):
    total, rows = expected(con, scope, n, where)
    text, df = engine.process(q)[:2]
    assert f": {total} عينة" in text.splitlines()[0]
    got = list(df[["pesticide", "samples_detected", "samples_above_limit"]].itertuples(index=False, name=None))
    assert got == rows


def test_dates_are_raw_varieties_only(engine):
    text, _ = engine.process("ما هي المبيدات الأكثر ظهوراً في التمور؟")[:2]
    assert "Date Paste" not in text and "Date Molasses" not in text and "Sukari Dates" in text


# ── Routing ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("qid_or_q", ["A023", "ما المبيدات في الكمون", "B009", "B039",
                                      "D002", "D010", "D011", "D019"])
def test_not_captured(engine, bank, qid_or_q):
    q = bank.get(qid_or_q, qid_or_q)
    assert engine._dispatch_top_pesticides(engine._extract_context(q)) is None


@pytest.mark.parametrize("q", ["ما هي العينات التي تحتوي على أكثر من ٥ مبيدات؟",
                               "أكثر المبيدات في العينات المطابقة"])
def test_more_than_n_and_compliant_scope_not_captured(engine, q):
    assert engine._dispatch_top_pesticides(engine._extract_context(q)) is None


@pytest.mark.parametrize("q, n", [
    ("أكثر 8 مبيدات ظهوراً في العينات غير المطابقة", 8),
    ("أكثر ٨ مبيدات ظهوراً في العينات غير المطابقة", 8),
    ("أكثر ثمانية مبيدات ظهوراً في العينات غير المطابقة", 8),
    ("أكثر ثمانِ مبيدات ظهوراً في العينات غير المطابقة", 8),
    ("أكثر عشرة مبيدات ظهوراً", 10),
    ("ما هي المبيدات الأكثر ظهوراً؟", 5),
])
def test_n_extraction(engine, q, n):
    _, df = engine.process(q)[:2]
    assert len(df) == n


# ── Periods ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("phrase, interval", [
    ("آخر شهر", "1 month"), ("آخر شهرين", "2 month"), ("آخر 3 شهور", "3 month"),
    ("آخر ٣ شهور", "3 month"), ("آخر ثلاثة أشهر", "3 month"), ("آخر أسبوع", "1 week"),
    ("آخر أسبوعين", "2 week"), ("آخر يومين", "2 day"), ("آخر 3 أيام", "3 day"),
])
def test_relative_periods(engine, con, phrase, interval):
    total, rows = expected(con, "all", 5, f"{DATE} >= {ANCHOR} - INTERVAL {interval}")
    text, df = engine.process(f"أكثر 5 مبيدات ظهوراً {phrase}")[:2]
    assert f": {total} عينة" in text.splitlines()[0]
    assert list(df[["pesticide", "samples_detected", "samples_above_limit"]]
                .itertuples(index=False, name=None)) == rows


def test_three_month_window_equals_report_handler(engine, con):
    report = engine.process("أعطني تقرير آخر 3 شهور")[0]
    ranking = engine.process("أكثر 5 مبيدات ظهوراً في آخر 3 شهور")[0]
    total = con.execute(f"""SELECT COUNT(DISTINCT "كود العينة") FROM chemistry_tidy
        WHERE {DATE} >= {ANCHOR} - INTERVAL 3 month""").fetchone()[0]
    assert total == 1149 and "**1149**" in report and ": 1149 عينة" in ranking


def test_absolute_month_single(engine, con):
    total = con.execute(f"""SELECT COUNT(DISTINCT "كود العينة") FROM chemistry_tidy
        WHERE date_part('month', {DATE}) = 3""").fetchone()[0]
    text = engine.process("أكثر 5 مبيدات ظهوراً في مارس")[0]
    assert total == 266 and ": 266 عينة" in text and "مارس" in text.splitlines()[0]


@pytest.mark.parametrize("q", ["أكثر 5 مبيدات ظهوراً من يناير إلى مارس",
                               "العينات غير المطابقة في يناير وفبراير",
                               "كم عينة غير مطابقة من يناير إلى مارس"])
def test_multi_month_refused_everywhere(engine, q):
    from modules.query.messages import MULTI_MONTH_MESSAGE
    text, df = engine.process(q)[:2]
    assert text == MULTI_MONTH_MESSAGE and df is None


def test_single_month_bank_questions_unchanged(engine, bank):
    for qid in ("B044", "D028"):
        assert "(filtered by period)" in engine.process(bank[qid])[0]


def test_month_name_inside_word_is_not_a_month(engine):
    assert engine._months_mentioned("عينات المايونيز") == set()


# ── Empty scope, wording, order ──────────────────────────────────────────────

def test_zero_scope_names_the_filters(engine):
    text, df = engine.process("أكثر 5 مبيدات في العينات غير المطابقة في بلدية الرس")[:2]
    assert df.empty and "لا توجد عينات غير مطابقة ضمن" in text and "بلدية الرس" in text
    assert "لم يتم العثور على مبيدات" not in text and "No pesticides" not in text


def test_eu_mrl_wording(engine):
    for q in ("أكثر 5 مبيدات ظهوراً في العينات غير المطابقة", "ما هي المبيدات الأكثر ظهوراً؟"):
        text = engine.process(q)[0]
        assert "تجاوزت الحد الأقصى الأوروبي (EU MRL)" in text and "اكتُشف في" in text
        assert "مخالف" not in text


def test_scope_orderings(engine):
    _, a = engine.process("ترتيب المبيدات حسب التكرار")[:2]
    _, b = engine.process("أكثر 10 مبيدات في العينات غير المطابقة")[:2]
    assert list(a["samples_detected"]) == sorted(a["samples_detected"], reverse=True)
    assert list(b["samples_above_limit"]) == sorted(b["samples_above_limit"], reverse=True)


def test_deterministic(engine):
    q = "أكثر 10 مبيدات في العينات غير المطابقة"
    answers = {engine.process(q)[0] for _ in range(5)}
    assert len(answers) == 1


# ── Category questions: refused ──────────────────────────────────────────────

@pytest.mark.parametrize("q", CATEGORY_QUESTIONS)
def test_category_questions_are_refused(engine, q):
    from modules.query.messages import CATEGORY_UNSUPPORTED_MESSAGE
    text, df = engine.process(q)[:2]
    assert text == CATEGORY_UNSUPPORTED_MESSAGE and df is None


@pytest.mark.parametrize("q, product", [("المبيدات الموجودة في الفستق", "Pistachios"),
                                        ("ما هي المبيدات الأكثر ظهوراً في الكمون؟", "Cumin"),
                                        ("كم عدد العينات غير المطابقة في الفستق؟", "Pistachios")])
def test_single_products_still_answer(engine, q, product):
    text, df = engine.process(q)[:2]
    assert df is not None and len(df) > 0 and product in text


@pytest.mark.parametrize("q", [
    "المبيدات الموجودة في الفستق",                      # product list: existing handler
    "ما هو متوسط عدد المبيدات في التوابل مقابل الخضراوات؟",  # C014 comparison
    "ما هي المبيدات التي لم تظهر إطلاقاً في الفواكه؟",       # A040 negation
])
def test_category_list_trigger_leaves_other_questions(engine, q):
    assert engine._dispatch_top_pesticides(engine._extract_context(q)) is None


def test_empty_scope_says_no_samples_not_no_pesticides(engine, con):
    """Dates in the last two days: 0 samples → the filter matched nothing."""
    text, _ = engine.process("هل ظهر الأبامكتين في التمر آخر يومين")[:2]
    assert "لا توجد عينات في البيانات تطابق" in text


def test_samples_without_detections_still_say_none_found(engine, con):
    """Cumin in the last two days: 4 samples, 0 detections → 'none found' is true."""
    n = con.execute(f"""SELECT COUNT(DISTINCT "كود العينة") FROM chemistry_tidy
        WHERE "اسم العينة" IN {CUMIN} AND {DATE} >= {ANCHOR} - INTERVAL 2 day""").fetchone()[0]
    text, _ = engine.process("ما هي المبيدات في الكمون آخر يومين")[:2]
    assert n == 4 and "لا توجد عينات في البيانات تطابق" not in text


# ── Category allow-list (Step 0) ─────────────────────────────────────────────

@pytest.mark.parametrize("qid", ["A021", "A023", "A045", "A046", "B022", "C014", "E007", "E016"])
def test_verified_category_answers_are_served(engine, bank, qid):
    """Correct at demo-freeze-2026-09 (checked against SQL) → restored."""
    from modules.query.messages import CATEGORY_UNSUPPORTED_MESSAGE
    text, df = engine.process(bank[qid])[:2]
    assert text != CATEGORY_UNSUPPORTED_MESSAGE and df is not None and len(df) > 0


@pytest.mark.parametrize("qid", ["A025", "A038", "A039", "A040", "B019", "B023", "B049", "D023"])
def test_unverified_category_answers_stay_refused(engine, bank, qid):
    """Wrong (or wrong metric) at the tag → the honest category refusal."""
    from modules.query.messages import CATEGORY_UNSUPPORTED_MESSAGE
    text, df = engine.process(bank[qid])[:2]
    assert text == CATEGORY_UNSUPPORTED_MESSAGE and df is None


@pytest.mark.parametrize("q", ["كم عدد العينات غير المطابقة في الخضروات؟",
                               "ما هي العينات غير المطابقة من الفواكه في جمعية البطين الزراعية؟"])
def test_generic_category_questions_refused_not_broadened(engine, q):
    """Handlers not verified for categories may ignore them and answer over
    all data; the allow-list refuses instead."""
    from modules.query.messages import CATEGORY_UNSUPPORTED_MESSAGE
    assert engine.process(q)[0] == CATEGORY_UNSUPPORTED_MESSAGE


# ── "أعلى/أبرز/أهم/أشهر N مبيدات" = top N, never "samples with N pesticides" ──

def expected_by_above(con, n, where):
    """Top N pesticides ranked by samples above the EU MRL, then detections."""
    return con.execute(f"""
        SELECT COALESCE(v.canon, lower(t.pesticide_name)) AS pesticide,
               COUNT(DISTINCT t."كود العينة") AS det,
               COUNT(DISTINCT CASE WHEN t.is_above_limit = 1 THEN t."كود العينة" END) AS above
        FROM chemistry_tidy t LEFT JOIN variants v ON lower(t.pesticide_name) = v.v
        WHERE {where} AND t.is_detected = 1 AND t.pesticide_name NOT IN ('NO DETECTION', 'NO DATA')
        GROUP BY 1 ORDER BY above DESC, det DESC, pesticide LIMIT {n}""").fetchall()


def ranking_rows(df):
    return list(df[["pesticide", "samples_detected", "samples_above_limit"]].itertuples(index=False, name=None))


@pytest.mark.parametrize("q, n, where", [
    ("ما هي أعلى خمس مبيدات في آخر شهرين؟", 5, f"{DATE} >= {ANCHOR} - INTERVAL 2 month"),   # voice bug
    ("أبرز 3 مبيدات في آخر شهر", 3, f"{DATE} >= {ANCHOR} - INTERVAL 1 month"),
    ("أهم ٧ مبيدات", 7, "1=1"),
    ("أشهر المبيدات", 5, "1=1"),
])
def test_top_words_rank_pesticides(engine, con, q, n, where):
    total, rows = expected(con, "all", n, where)
    text, df = engine.process(q)[:2]
    assert engine._refusal is None and [c[0] for c in engine._handlers_called] == ["_handle_top_pesticides"]
    assert f": {total} عينة" in text.splitlines()[0] and ranking_rows(df) == rows


@pytest.mark.parametrize("qid", ["D005", "D029"])            # "من حيث عدد المخالفات"
def test_top_by_violations_ranks_by_above_limit(engine, con, bank, qid):
    text, df = engine.process(bank[qid])[:2]
    assert "تجاوزاً للحد الأقصى الأوروبي (EU MRL)" in text
    assert ranking_rows(df) == expected_by_above(con, 5, "1=1")


@pytest.mark.parametrize("q", ["أعلى 5 مبيدات في الخضار", "أهم 10 مبيدات في التوابل"])
def test_top_words_in_a_category_are_refused(engine, q):
    from modules.query.messages import CATEGORY_UNSUPPORTED_MESSAGE
    assert engine.process(q)[0] == CATEGORY_UNSUPPORTED_MESSAGE      # live: semantic answers


def test_months_are_not_a_ranking(engine):
    assert not engine._top_pesticide_phrase("ما هي المبيدات في اخر 3 اشهر المبيدات")
    assert engine._top_pesticide_phrase("اشهر 5 مبيدات")


# N-pesticides handlers only for "samples containing N pesticides"
@pytest.mark.parametrize("qid", ["B030", "C015", "D006"])
def test_n_pesticides_misroutes_are_refused(engine, bank, qid):
    text, df = engine.process(bank[qid])[:2]
    assert engine._refusal == "n_pesticides_not_asked" and df is None


@pytest.mark.parametrize("q", ["كم عينة فيها 5 مبيدات", "ما هو عدد العينات التي تحتوي على ٦ مبيدات؟",
                               "ما هي العينات التي وصلت للحد الأقصى ١٠ متبقيات؟",
                               "ما هي العينات الخالية تماماً من المبيدات؟", "عينات بمبيدين",
                               "samples with 3 pesticides"])
def test_samples_with_n_pesticides_still_answer(engine, q):
    from modules.query.text_norm import asks_samples_with_n_pesticides
    _, df = engine.process(q)[:2]
    assert asks_samples_with_n_pesticides(q) and engine._refusal is None and df is not None
    assert any("n_pesticides" in c[0] for c in engine._handlers_called)


@pytest.mark.parametrize("q", ["أعلى 5 مبيدات", "ما هي أعلى ١٠ مبيدات من حيث نسبة المخالفة؟",
                               "ما هي المنتجات التي متوسط عدد مبيداتها أعلى من ٤؟"])
def test_rankings_do_not_ask_for_samples_with_n(q):
    from modules.query.text_norm import asks_samples_with_n_pesticides
    assert not asks_samples_with_n_pesticides(q)
