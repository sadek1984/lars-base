"""
Batch 3 — determinism, rate breakdowns routed to the right handler, date scope.

Expected values are recomputed with independent SQL against
lars_data_demo.duckdb (read-only).

Run:  pytest tests/test_batch3.py -v
"""
import csv
import logging
import subprocess
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

VS = 'COUNT(DISTINCT CASE WHEN is_above_limit = 1 THEN "كود العينة" END)'
RATE = f'ROUND(100.0 * {VS} / COUNT(DISTINCT "كود العينة"), 1)'


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect(str(DB_PATH), read_only=True)
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


def rows(con, sql, params=()):
    return con.execute(sql, list(params)).fetchall()


# ── 1. Determinism ───────────────────────────────────────────────────────────

def test_whole_bank_is_deterministic_across_seeds_and_question_order():
    """Every bank question, in a fresh process per PYTHONHASHSEED (1, 2, 3),
    plus the whole bank forward then reversed in one engine instance:
    reply text and result table (row order included) must be identical."""
    proc = subprocess.run(
        [sys.executable, str(REPO / "phase0" / "check_determinism.py"), "--seeds", "1", "2", "3"],
        capture_output=True, text=True, timeout=900,
    )
    assert proc.returncode == 0, proc.stdout[-4000:] + proc.stderr[-2000:]
    assert "Varying: 0" in proc.stdout


def test_E001_stats_combine_every_spelling(engine, bank, con):
    """Was: GROUP BY pesticide_name + df.iloc[0] with no ORDER BY, so the reply
    was whichever spelling DuckDB returned first (359, 3 or 1 detections)."""
    _, df = engine.process(bank["E001"])[:2]
    n, lo, hi = rows(con, """SELECT COUNT(*), ROUND(MIN(concentration), 4), ROUND(MAX(concentration), 4)
        FROM chemistry_tidy WHERE is_detected = 1 AND lower(pesticide_name) LIKE 'imidac%'""")[0]
    assert n == 367
    assert (int(df["detections"].iloc[0]), df["min_concentration"].iloc[0], df["max_concentration"].iloc[0]) \
        == (n, pytest.approx(lo), pytest.approx(hi))


def test_E007_stats_scoped_to_spices(engine, bank, con):
    text, df = engine.process(bank["E007"])[:2]
    n, sd = rows(con, """SELECT COUNT(*), ROUND(STDDEV_SAMP(concentration), 4) FROM chemistry_tidy
        WHERE is_detected = 1 AND lower(pesticide_name) LIKE 'carbend%' AND "نوع العينة" = 'Spices'""")[0]
    assert int(df["detections"].iloc[0]) == n
    assert df["std_concentration"].iloc[0] == pytest.approx(sd)
    assert "All sample types" not in text


def test_E007_answer_does_not_depend_on_previous_questions(bank):
    """Fresh engine per ordering: E007 first, and after other question types."""
    from modules.query.core_query_engine import CoreQueryEngine
    answers = set()
    for before in ([], ["E001"], ["D026"], ["A052", "D012", "B040"]):
        e = CoreQueryEngine(db_path=str(DB_PATH))
        for q in before:
            e.process(bank[q])
        text, df = e.process(bank["E007"])[:2]
        answers.add((text, df.to_csv(index=False)))
    assert len(answers) == 1


# ── 2. Rate breakdowns ───────────────────────────────────────────────────────

def test_D011_rate_per_municipality(engine, bank, con):
    text, df = engine.process(bank["D011"])[:2]
    expected = rows(con, f"""SELECT "اسم البلدية", COUNT(DISTINCT "كود العينة"), {VS}, {RATE} AS r
        FROM chemistry_tidy WHERE "اسم البلدية" IS NOT NULL
        GROUP BY 1 HAVING COUNT(DISTINCT "كود العينة") >= 10 ORDER BY r DESC, 1""")
    got = list(df[["entity_name", "total_samples", "violating_samples", "violation_rate_pct"]]
               .itertuples(index=False, name=None))
    assert got == [(m, s, v, pytest.approx(r)) for m, s, v, r in expected]
    assert "أقل من 10 عينات" in text


def test_D019_monthly_trend_is_chronological(engine, bank, con):
    _, df = engine.process(bank["D019"])[:2]
    expected = rows(con, f"""SELECT strftime(strptime("التاريخ", '%d/%m/%Y'), '%Y-%m') AS m,
        COUNT(DISTINCT "كود العينة"), {VS}, {RATE}
        FROM chemistry_tidy WHERE "التاريخ" IS NOT NULL GROUP BY m ORDER BY m""")
    got = list(df[["period", "sample_count", "violating_samples", "violation_rate_pct"]]
               .itertuples(index=False, name=None))
    assert got == [(m, s, v, pytest.approx(r)) for m, s, v, r in expected]


def test_D010_top_5_neighborhoods_by_rate_with_threshold(engine, bank, con):
    text, df = engine.process(bank["D010"])[:2]
    expected = rows(con, f"""SELECT "الحى", {RATE} AS r FROM chemistry_tidy
        WHERE "الحى" IS NOT NULL AND "الحى" != ''
        GROUP BY 1 HAVING COUNT(DISTINCT "كود العينة") >= 10 ORDER BY r DESC, 1 LIMIT 5""")
    assert list(zip(df["entity_name"], df["violation_rate_pct"])) == [(h, pytest.approx(r)) for h, r in expected]
    assert (df["total_samples"] >= 10).all()
    assert "أقل من 10 عينات" in text


# ── 3. Dates ─────────────────────────────────────────────────────────────────

RAW_DATES = ["Dates", "Khlas Dates", "Saqai Dates", "Sukari Dates", "Wanana Dates"]


@pytest.mark.parametrize("q", ["عينات التمر", "ما هي المبيدات في التمور", "dates samples"])
def test_dates_resolve_to_raw_varieties_only(engine, q):
    assert engine._get_resolver().resolve(q).products == RAW_DATES


@pytest.mark.parametrize("q, product", [
    ("دبس التمر", "Date Molasses"), ("عينات الدبس", "Date Molasses"),
    ("عجينة التمر", "Date Paste"), ("مسحوق التمر", "Date Powder"),
])
def test_processed_date_products_only_when_named(engine, q, product):
    assert engine._get_resolver().resolve(q).products == [product]


def test_other_processed_merges_unchanged(engine):
    """Batch 3 scope: only dates change. Pistachio Powder stays under الفستق."""
    assert engine._get_resolver().resolve("عينات الفستق").products == ["Pistachio Powder", "Pistachios"]


def test_E016_compares_both_categories(engine, bank, con):
    _, df = engine.process(bank["E016"])[:2]
    expected = rows(con, """SELECT "نوع العينة", COUNT(*), ROUND(AVG(concentration), 4) FROM chemistry_tidy
        WHERE is_detected = 1 AND lower(pesticide_name) LIKE 'carbend%'
          AND "نوع العينة" IN ('Spices', 'Vegetables') GROUP BY 1 ORDER BY 1""")
    assert list(zip(df["detections"], df["avg_concentration"])) == [(n, pytest.approx(a)) for _, n, a in expected]
