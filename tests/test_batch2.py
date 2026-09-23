"""
Batch 2 — rate correctness, facility routing, category handlers, error hygiene,
product scope.

Expected values are recomputed here with independent SQL against
lars_data_demo.duckdb (read-only) and, where the audit recorded a figure,
pinned to it.

Run:  pytest tests/test_batch2.py -v
"""
import csv
import logging
import re
import sys
from pathlib import Path

import duckdb
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
LARS = REPO / "src" / "LARS"
DB_PATH = LARS / "data" / "lars_data_demo.duckdb"
BANK = REPO / "phase0" / "questions_bank.csv"
sys.path.insert(0, str(LARS))

pytestmark = pytest.mark.skipif(not DB_PATH.exists(), reason="lars_data_demo.duckdb not present")

ERROR_TEXT = re.compile(r"(Binder|Catalog|Parser|Conversion) Error|Traceback|تعذر تنفيذ الاستعلام")
# Sample-level violation rate: samples with any exceedance / samples.
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


def assert_rates_in_range(df, col="violation_rate_pct"):
    assert df is not None and not df.empty
    assert df[col].between(0, 100).all(), df[col].describe()


# ── 1. Rates ─────────────────────────────────────────────────────────────────

def test_D012_municipality_rate_is_sample_level(engine, bank, con):
    _, df = engine.process(bank["D012"])[:2]
    expected = dict(rows(con, f"""SELECT "اسم البلدية", {RATE} FROM chemistry_tidy
        WHERE "اسم البلدية" IN ('بلدية شرق بريدة', 'بلدية غرب بريدة') GROUP BY 1"""))
    got = dict(zip(df["municipality"], df["violation_rate_pct"]))
    assert got == pytest.approx(expected)
    assert_rates_in_range(df)


@pytest.mark.parametrize("call", [
    lambda e: e._handle_neighborhood_ranking(),
    lambda e: e._handle_top_n_by_metric("product", "rate", 50),
    lambda e: e._handle_top_n_by_metric("facility", "count", 50),
    lambda e: e._handle_time_series_breakdown("month"),
    lambda e: e._handle_violations_threshold([], [], 0, "spice"),
], ids=["neighborhood", "top_product_rate", "top_facility", "monthly", "threshold_spices"])
def test_every_touched_rate_handler_stays_within_0_100(engine, call):
    _, df = call(engine)
    assert_rates_in_range(df)


def test_top_products_by_rate_match_independent_sql(engine, con):
    _, df = engine._handle_top_n_by_metric("product", "rate", 5)
    expected = rows(con, f"""SELECT "اسم العينة", {RATE} AS r FROM chemistry_tidy
        WHERE "اسم العينة" IS NOT NULL GROUP BY 1 HAVING COUNT(DISTINCT "كود العينة") >= 5
        ORDER BY r DESC LIMIT 5""")
    assert list(df["violation_rate_pct"]) == pytest.approx([r for _, r in expected])


def test_guard_rejects_out_of_range_percentages(engine):
    from modules.query.messages import CANNOT_COMPUTE_RATE_MESSAGE
    bad = pd.DataFrame({"municipality": ["x"], "violation_rate_pct": [126.0]})
    text, df = engine._guard_percentages("answer", bad)
    assert text == CANNOT_COMPUTE_RATE_MESSAGE and df is None


def test_guard_allows_percent_of_mrl_above_100(engine):
    ok = pd.DataFrame({"pesticide": ["x"], "pct_of_mrl": [250.0], "violation_rate_pct": [40.0]})
    text, df = engine._guard_percentages("answer", ok)
    assert text == "answer" and df is ok


# ── 2. Facility routing, headline totals, associations ──────────────────────

def test_D002_headline_totals(engine, bank, con):
    _, df = engine.process(bank["D002"])[:2]
    unique, records = rows(con, 'SELECT COUNT(DISTINCT "كود العينة"), COUNT(*) FROM chemistry_tidy')[0]
    assert (unique, records) == (1859, 6811)
    assert int(df["unique_samples"].iloc[0]) == unique
    assert int(df["total_records"].iloc[0]) == records


def test_A052_association_resolves_to_municipality_column(engine, bank, con):
    _, df = engine.process(bank["A052"])[:2]
    expected = rows(con, """SELECT COUNT(DISTINCT "كود العينة") FROM chemistry_tidy
        WHERE "اسم البلدية" = 'جمعية البطين الزراعية'""")[0][0]
    assert expected == 101
    assert int(df["sample_count"].sum()) == expected


def test_B039_non_compliant_in_association(engine, bank, con):
    _, df = engine.process(bank["B039"])[:2]
    samples, nc = rows(con, """SELECT COUNT(DISTINCT "كود العينة"),
        COUNT(DISTINCT CASE WHEN sample_result = 'Non-Compliant' THEN "كود العينة" END)
        FROM chemistry_tidy WHERE "اسم البلدية" = 'جمعية البطين الزراعية'""")[0]
    assert (samples, nc) == (101, 7)
    assert int(df["sample_count"].sum()) == samples
    assert int(df["non_compliant"].sum()) == nc


def test_real_facility_still_uses_facility_search(engine, con):
    name = "شركة السنابل للمواد الغذائية التجارية"
    text, df = engine.process(f"ابحث عن عينات {name}")[:2]
    expected = rows(con, """SELECT COUNT(*) FROM chemistry_tidy
        WHERE is_detected = 1 AND "اسم المنشاة" = ?""", [name])[0][0]
    assert "Facility search" in text
    assert len(df) == min(expected, 50) and set(df["facility_name"]) == {name}


def test_facility_keyword_without_a_facility_does_not_search(engine):
    text, _ = engine.process("كم إجمالي العينات المستلمة وكم عينة فريدة؟")[:2]
    assert "Facility search" not in text and "No samples found in a facility" not in text


# ── 3. Category handlers on the resolver ─────────────────────────────────────

def test_exceedance_multiplier_by_category(engine, con):
    _, df = engine._handle_exceedance_multiplier([], 3.0, "spice")
    expected = rows(con, """SELECT COUNT(*) FROM chemistry_tidy WHERE is_detected = 1
        AND limit_value > 0 AND exceedance_ratio >= 3.0 AND "نوع العينة" = 'Spices'""")[0][0]
    assert len(df) == min(expected, 100) and expected > 0


def test_category_comparison_violations(engine, con):
    _, df = engine._handle_category_comparison("spice", "vegetable", "violations")
    expected = dict(rows(con, f"""SELECT "نوع العينة", {RATE} FROM chemistry_tidy
        WHERE "نوع العينة" IN ('Spices', 'Vegetables') GROUP BY 1"""))
    assert list(df["violation_rate_pct"]) == pytest.approx([expected["Spices"], expected["Vegetables"]])


def test_category_violation_share(engine, con):
    _, df = engine._handle_category_violation_share("spice")
    cat, total = rows(con, """SELECT
        (SELECT SUM(violation_count) FROM sample_summary WHERE sample_category = 'Spices'),
        (SELECT SUM(violation_count) FROM sample_summary)""")[0]
    assert int(df["category_violations"].iloc[0]) == cat
    assert float(df["share_pct"].iloc[0]) == pytest.approx(round(100.0 * cat / total, 1))


def test_category_vs_overall_rate(engine, con):
    _, df = engine._handle_category_vs_overall_rate("spice")
    cat = rows(con, f"""SELECT {RATE} FROM chemistry_tidy WHERE "نوع العينة" = 'Spices'""")[0][0]
    overall = rows(con, f"SELECT {RATE} FROM chemistry_tidy")[0][0]
    assert float(df["category_rate"].iloc[0]) == pytest.approx(cat)
    assert float(df["overall_rate"].iloc[0]) == pytest.approx(overall)
    assert 0 <= cat <= 100 and 0 <= overall <= 100


# ── 4. No raw errors ─────────────────────────────────────────────────────────

def test_D026_poisoning_trend_answers_without_error(engine, bank, con):
    text, df = engine.process(bank["D026"])[:2]
    assert not ERROR_TEXT.search(text)
    months = rows(con, """SELECT COUNT(DISTINCT date_trunc('month', incident_date))
        FROM poisoning_incidents WHERE incident_date IS NOT NULL""")[0][0]
    assert len(df) == months


def test_handler_exception_becomes_polite_message(engine, bank, monkeypatch):
    from modules.query.messages import POLITE_ERROR_MESSAGE

    def boom(*a, **k):
        raise ValueError("Binder Error: simulated failure")
    monkeypatch.setattr(engine, "_handle_headline_totals", boom)
    text, df = engine.process(bank["D002"])[:2]
    assert text == POLITE_ERROR_MESSAGE and df is None
    assert not ERROR_TEXT.search(text)


# ── 5. Product scope ─────────────────────────────────────────────────────────

def test_almonds_exclude_almond_tahini(engine):
    resolver = engine._get_resolver()
    assert resolver.resolve("عينات اللوز").products == ["Almonds"]
    assert "Almond Tahini" in resolver.resolve("عينات الطحينة").products
    assert resolver.resolve("عينات طحينة اللوز").products == ["Almond Tahini"]


def test_B040_municipality_not_read_as_neighborhood_and_totals_are_distinct(engine, bank, con):
    """'بلدية الصفراء الفرعية' used to also match the neighborhood 'الصفراء' (51
    samples), and the headline total summed per-product counts, which
    over-counts codes shared across product names."""
    text, _ = engine.process(bank["B040"])[:2]
    samples, nc = rows(con, """SELECT COUNT(DISTINCT "كود العينة"),
        COUNT(DISTINCT CASE WHEN sample_result = 'Non-Compliant' THEN "كود العينة" END)
        FROM chemistry_tidy WHERE "اسم البلدية" = 'بلدية الصفراء الفرعية'""")[0]
    assert f"Total unique samples: **{samples}**" in text
    assert f"Non-Compliant: {nc}**" in text
