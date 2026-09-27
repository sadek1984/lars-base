"""
Semantic layer, Phase 1: catalog, category/analyte tables, QuerySpec, periods.

Expected values are recomputed with independent SQL against
lars_data_demo.duckdb (read-only).

Run:  pytest tests/test_semantic_phase1.py -v
"""
import csv
import sys
from datetime import date
from pathlib import Path

import duckdb
import pytest
from pydantic import ValidationError

REPO = Path(__file__).resolve().parents[1]
LARS = REPO / "src" / "LARS"
DB_PATH = LARS / "data" / "lars_data_demo.duckdb"
sys.path.insert(0, str(LARS))

pytestmark = pytest.mark.skipif(not DB_PATH.exists(), reason="lars_data_demo.duckdb not present")

from modules.semantic.query_spec import Period, QuerySpec  # noqa: E402
from modules.semantic.tables import category_key  # noqa: E402


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect(str(DB_PATH), read_only=True)
    yield c
    c.close()


@pytest.fixture(scope="module")
def catalog():
    from modules.semantic.catalog import build_catalog
    return build_catalog(str(DB_PATH))


def count_between(con, lo, hi):
    return con.execute("""SELECT COUNT(DISTINCT "كود العينة") FROM chemistry_tidy
        WHERE test_date BETWEEN ? AND ?""", [lo, hi]).fetchone()[0]


# ── Catalog ──────────────────────────────────────────────────────────────────

def test_catalog_matches_db(catalog, con):
    cats = dict(con.execute("""SELECT "نوع العينة", COUNT(DISTINCT "كود العينة") FROM chemistry_tidy
        WHERE "نوع العينة" IS NOT NULL GROUP BY 1""").fetchall())
    assert catalog.categories == cats
    assert catalog.categories["Vegetables"] == 727 and catalog.categories["Spices"] == 479
    assert (len(catalog.products), len(catalog.municipalities), len(catalog.neighborhoods)) == (108, 9, 54)
    assert (catalog.min_date, catalog.max_date) == (date(2026, 1, 5), date(2026, 5, 17))
    assert catalog.total_samples == 1859


def test_test_date_equals_the_parsed_lab_date(con):
    assert con.execute("""SELECT COUNT(*) FROM chemistry_tidy
        WHERE test_date IS DISTINCT FROM CAST(strptime("التاريخ", '%d/%m/%Y') AS DATE)""").fetchone()[0] == 0


# ── Tables ───────────────────────────────────────────────────────────────────

def test_analyte_map_covers_every_raw_name(catalog, con):
    raw = {r[0] for r in con.execute(
        "SELECT DISTINCT pesticide_name FROM chemistry_tidy WHERE pesticide_name IS NOT NULL").fetchall()}
    assert set(catalog.analytes.raw_to_canonical) == raw


def test_analyte_map_merges_spellings(catalog):
    a = catalog.analytes
    assert len(a.raw_names("acetamiprid")) == 8
    assert a.raw_to_canonical["Afla B1"] == a.raw_to_canonical["aflaB1"] == "aflatoxin B1"
    assert a.canonical_class["aflatoxin B1"] == "mycotoxin"
    assert a.raw_to_canonical["profenfos"] == "profenofos"
    assert a.raw_to_canonical["NO CBD"] == "" and "" not in a.canonical_class


def test_merged_detections_are_the_sum_of_their_spellings(catalog, con):
    raws = catalog.analytes.raw_names("acetamiprid")
    merged = con.execute(f"""SELECT COUNT(*) FROM chemistry_tidy WHERE is_detected = 1
        AND pesticide_name IN ({",".join("?" * len(raws))})""", raws).fetchone()[0]
    assert merged == con.execute("""SELECT COUNT(*) FROM chemistry_tidy WHERE is_detected = 1
        AND lower(pesticide_name) IN ('acetamiprid','acatamiprid','accetamiprid','acetamaiprid',
        'acetamipeid','acrtamiprid','aetamiprid','azcetamiprid')""").fetchone()[0] == 376


def test_non_analytes_are_never_detections(catalog, con):
    non = sorted(r for r, c in catalog.analytes.raw_to_canonical.items() if c == "")
    assert con.execute(f"""SELECT COALESCE(SUM(is_detected), 0) FROM chemistry_tidy
        WHERE pesticide_name IN ({",".join("?" * len(non))})""", non).fetchone()[0] == 0


def test_category_terms_resolve_with_or_without_article(catalog):
    assert catalog.category_terms[category_key("التوابل")] == ("Spices",)
    assert catalog.category_terms[category_key("توابل")] == ("Spices",)
    assert catalog.category_terms[category_key("الخضار الورقية")] == ("Leafy Greens",)


# ── Periods (anchored on MAX(test_date)) ─────────────────────────────────────

def test_last_3_months_is_1149(catalog, con):
    lo, hi = Period(type="relative", n=3, unit="month").bounds(catalog.max_date)
    independent = con.execute("""SELECT COUNT(DISTINCT "كود العينة") FROM chemistry_tidy
        WHERE test_date >= (SELECT MAX(test_date) FROM chemistry_tidy) - INTERVAL 3 month""").fetchone()[0]
    assert count_between(con, lo, hi) == independent == 1149


def test_january_to_march_is_1111(con):
    lo, hi = Period(type="range", start="2026-01-01", end="2026-03-31").bounds(date(2026, 5, 17))
    assert count_between(con, lo, hi) == 1111


def test_absolute_month(con):
    assert Period(type="absolute_month", month=2).bounds(date(2026, 5, 17)) == (date(2026, 2, 1), date(2026, 2, 28))
    assert Period(type="absolute_month", month=12, year=2025).bounds(date(2026, 5, 17)) == (date(2025, 12, 1), date(2025, 12, 31))


# ── QuerySpec schema ─────────────────────────────────────────────────────────

def test_spec_defaults():
    s = QuerySpec(metric="top_pesticides")
    assert (s.top_n, s.scope.value, s.sort.value, s.period.type.value, s.unsupported) == (5, "all", "desc", "none", False)


@pytest.mark.parametrize("bad", [
    {"metric": "sql", },
    {"metric": "sample_count", "sql": "SELECT 1"},                                 # extra field
    {"metric": "sample_count", "filters": {"table": "x"}},
    {"metric": "sample_count", "unsupported": True},                                # no reason
    {"metric": "sample_count", "period": {"type": "relative", "n": 3}},             # no unit
    {"metric": "sample_count", "period": {"type": "absolute_month", "month": 13}},
    {"metric": "sample_count", "period": {"type": "none", "month": 3}},
    {"metric": "sample_count", "period": {"type": "range", "start": "2026-03-31", "end": "2026-01-01"}},
    {"metric": "top_pesticides", "top_n": 0},
    {"metric": "noncompliant_count", "mrl_multiple": 2},                             # multiple only for above-limit
])
def test_spec_rejects(bad):
    with pytest.raises(ValidationError):
        QuerySpec.model_validate(bad)


def test_spec_round_trips_json():
    s = QuerySpec(metric="noncompliance_rate", filters={"category": ["التوابل"]}, group_by="category",
                  period={"type": "relative", "n": 3, "unit": "month"})
    assert QuerySpec.model_validate_json(s.model_dump_json()) == s
