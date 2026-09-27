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
    ("وش المبيدات اللي في العينات اللي ما طابقت في الخضروات؟", "nc", 5, "\"نوع العينة\" = 'Vegetables'"),
    ("ما المبيدات التي سببت عدم المطابقة في الكمون؟", "nc", 5, f"\"اسم العينة\" IN {CUMIN}"),
    ("أكثر 3 مبيدات في العينات غير المطابقة في بلدية شرق بريدة", "nc", 3,
     "\"اسم البلدية\" = 'بلدية شرق بريدة'"),
    ("ما هي المبيدات الأكثر ظهوراً في الخضروات؟", "all", 5, "\"نوع العينة\" = 'Vegetables'"),
    ("ما هي المبيدات الأكثر ظهوراً في المكسرات؟", "all", 5, "\"نوع العينة\" = 'Nuts'"),
    ("أكثر 10 مبيدات ظهوراً في الفواكه في مارس", "all", 10,
     f"\"نوع العينة\" = 'Fruits' AND date_part('month', {DATE}) = 3"),
    ("ترتيب المبيدات حسب التكرار", "all", 5, "1=1"),
    # bank questions of this intent that were answered wrongly before (approved)
    ("ما هي أكثر ١٠ مبيدات تكراراً في التوابل؟", "all", 10, "\"نوع العينة\" = 'Spices'"),
    ("ما هي أكثر ٥ مبيدات تكراراً في الخضراوات؟", "all", 5, "\"نوع العينة\" = 'Vegetables'"),
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


def test_nuts_resolve_to_the_category_not_mixed_nuts(engine, con):
    text, df = engine.process("ما هي المبيدات الأكثر ظهوراً في المكسرات؟")[:2]
    assert "Mixed Nuts" not in text and len(df) == 5
    assert con.execute("""SELECT COUNT(*) FROM chemistry_tidy WHERE "نوع العينة" = 'Nuts'
        AND is_detected = 1""").fetchone()[0] > 0


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


# ── Category pesticide lists (same branch, follow-up) ────────────────────────

@pytest.mark.parametrize("q, category", [
    ("المبيدات الموجودة في المكسرات", "Nuts"),
    ("ما هي المبيدات في الخضروات؟", "Vegetables"),
    ("ما هي المبيدات التي ظهرت في الفواكه؟", "Fruits"),
    ("وش المبيدات اللي في التوابل؟", "Spices"),
])
def test_category_list_matches_sql(engine, con, q, category):
    """Every pesticide in the category, not just a top N, and never
    'no pesticides found' (nuts used to resolve to 'Mixed Nuts')."""
    where = f"\"نوع العينة\" = '{category}'"
    total, rows = expected(con, "all", 1000, where)
    text, df = engine.process(q)[:2]
    assert f": {total} عينة" in text.splitlines()[0]
    got = list(df[["pesticide", "samples_detected", "samples_above_limit"]].itertuples(index=False, name=None))
    assert got == rows and len(got) > 0
    assert "No pesticides found" not in text and "Mixed Nuts" not in text


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
