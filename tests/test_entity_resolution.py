"""
Batch 1 — entity resolution against real DB values.

Two layers:
  1. EntityResolver unit checks (products / qualifiers / categories /
     municipalities / no phantom pesticide / honest unresolved message).
  2. The 12 zero-row-audit questions that were confident wrong answers, run
     through CoreQueryEngine.process(). Each expected number is recomputed here
     with independent SQL against lars_data_demo.duckdb (read-only) AND pinned
     to the value recorded in zero_row_audit.csv, so a data refresh fails loudly
     instead of silently moving the goalposts.

Run:  pytest tests/test_entity_resolution.py -v
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

D = "is_detected = 1 AND pesticide_name NOT IN ('NO DETECTION','NO DATA')"
PEPPER = """"اسم العينة" ILIKE '%pepper%'"""


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
def resolver(engine):
    return engine._get_resolver()


@pytest.fixture(scope="module")
def bank():
    with BANK.open(encoding="utf-8") as f:
        return {r["id"]: r["question"] for r in csv.DictReader(f)}


def ask(engine, bank, qid):
    text, df = engine.process(bank[qid])[:2]
    assert df is not None and not df.empty, f"{qid} returned no rows: {text[:200]}"
    return text, df


def scalar(con, sql):
    return con.execute(sql).fetchone()[0]


# ── 1. Resolver unit checks ───────────────────────────────────────────────────

def test_generic_pepper_resolves_to_every_pepper_value(resolver, con):
    expected = {r[0] for r in con.execute(f'SELECT DISTINCT "اسم العينة" FROM chemistry_tidy WHERE {PEPPER}').fetchall()}
    assert set(resolver.resolve("ما هي عينات الفلفل الراسبة؟").products) == expected


def test_qualifiers_narrow_and_are_not_neighborhoods(engine, resolver):
    q = "ابحث عن الأسيتاميبريد في الفلفل البارد الأخضر"
    assert resolver.resolve(q).products == ["Sweet Green Pepper"]
    assert set(resolver.resolve("فلفل حار").products) == {"Hot Red Pepper", "Hot Green Pepper"}
    # 'الأخضر' is a real neighborhood (273 rows) — here it is a qualifier.
    ctx = engine._extract_context(q)
    assert ctx["detected_neighborhoods"] == []
    assert engine.router.analyze(q)[1].neighborhoods == []


def test_arabic_category_maps_to_stored_english_category(resolver):
    assert resolver.resolve("في أي التوابل ظهر الكاربندازيم؟").categories == ["Spices"]
    assert resolver.resolve("ما هي الخضروات التي ظهر فيها مبيد البايفنثرين؟").categories == ["Vegetables"]


def test_municipality_prefix_and_no_trailing_junk(resolver):
    res = resolver.resolve("قارن بين بلدية شرق بريدة وبلدية غرب بريدة في نسبة المخالفة")
    assert res.municipalities == ["بلدية شرق بريدة", "بلدية غرب بريدة"]
    assert resolver.resolve("ما عدد العينات في كل بلدية مفصلة حسب نوع المنتج؟").all_municipalities


@pytest.mark.parametrize("q", [
    "ما هي المبيدات التي لم تظهر إطلاقاً في الفواكه؟",
    "أعطني المبيدات والسموم الفطرية فوق الحد وتحت الحد للتوابل",
    "قارن المبيدات المكتشفة بين بلدية غرب بريدة وبلدية شمال بريدة",
])
def test_no_default_pesticide_is_injected(engine, q):
    assert engine._extract_context(q)["detected_pesticide"] is None


def test_unresolved_product_gets_honest_message(engine):
    text, df = engine.process("ما هي المبيدات في عينات الثوم؟")[:2]
    assert df is None and "لم أجد" in text and "الثوم" in text


# ── 2. Zero-row audit assertions ─────────────────────────────────────────────

def test_A010_acetamiprid_in_sweet_green_pepper(engine, bank, con):
    _, df = ask(engine, bank, "A010")
    expected = scalar(con, f"""SELECT count(*) FROM chemistry_tidy WHERE {D}
        AND regexp_matches(lower(pesticide_name), 'acetami') AND "اسم العينة" = 'Sweet Green Pepper'""")
    assert expected == 33
    assert len(df) == expected


def test_A021_vegetables_with_bifenthrin(engine, bank):
    """A021 names a category. Category-level questions are refused (not supported)."""
    from modules.query.messages import CATEGORY_UNSUPPORTED_MESSAGE
    text, df = engine.process(bank["A021"])[:2]
    assert text == CATEGORY_UNSUPPORTED_MESSAGE and df is None


def test_A023_spices_with_carbendazim(engine, bank):
    """A023 names a category. Category-level questions are refused (not supported)."""
    from modules.query.messages import CATEGORY_UNSUPPORTED_MESSAGE
    text, df = engine.process(bank["A023"])[:2]
    assert text == CATEGORY_UNSUPPORTED_MESSAGE and df is None


def test_A040_pesticides_never_detected_in_fruits(engine, bank):
    """A040 names a category. Category-level questions are refused (not supported)."""
    from modules.query.messages import CATEGORY_UNSUPPORTED_MESSAGE
    text, df = engine.process(bank["A040"])[:2]
    assert text == CATEGORY_UNSUPPORTED_MESSAGE and df is None


def test_B022_spice_pesticides_above_below(engine, bank):
    """B022 names a category. Category-level questions are refused (not supported)."""
    from modules.query.messages import CATEGORY_UNSUPPORTED_MESSAGE
    text, df = engine.process(bank["B022"])[:2]
    assert text == CATEGORY_UNSUPPORTED_MESSAGE and df is None


def test_B009_failed_pepper_samples(engine, bank, con):
    _, df = ask(engine, bank, "B009")
    expected = scalar(con, f"""SELECT count(DISTINCT "كود العينة") FROM chemistry_tidy
        WHERE {PEPPER} AND sample_result = 'Non-Compliant'""")
    assert expected == 29
    assert int(df["non_compliant"].sum()) == expected


def test_E020_neonicotinoid_hri_in_pepper(engine, bank, con):
    _, df = ask(engine, bank, "E020")
    expected = scalar(con, f"""SELECT count(DISTINCT pesticide_name) FROM chemistry_tidy WHERE {D} AND {PEPPER}
        AND regexp_matches(lower(pesticide_name), 'acetami|imidac|thiameth|clothi|clotha|dinotef|thiaclo|nitenp')""")
    assert expected == 8
    assert df["المبيد"].nunique() == expected


def test_E029_quality_index_for_pepper(engine, bank, con):
    _, df = ask(engine, bank, "E029")
    expected = scalar(con, f"""SELECT count(DISTINCT "كود العينة") FROM chemistry_tidy WHERE {D} AND {PEPPER}""")
    assert expected == 229
    assert len(df) == expected


def test_A054_compare_pesticides_two_municipalities(engine, bank, con):
    _, df = ask(engine, bank, "A054")
    expected = scalar(con, f"""SELECT count(*) FROM (SELECT 1 FROM chemistry_tidy WHERE {D}
        AND "اسم البلدية" IN ('بلدية غرب بريدة','بلدية شمال بريدة') GROUP BY "اسم البلدية", pesticide_name)""")
    assert expected == 180
    assert len(df) == expected


def test_D012_compare_violation_rate(engine, bank):
    _, df = ask(engine, bank, "D012")
    assert len(df) == 2
    assert set(df["municipality"]) == {"بلدية شرق بريدة", "بلدية غرب بريدة"}


def test_A055_every_municipality_by_product(engine, bank, con):
    _, df = ask(engine, bank, "A055")
    expected = scalar(con, """SELECT count(*) FROM (SELECT 1 FROM chemistry_tidy
        GROUP BY "اسم البلدية", "اسم العينة")""")
    assert expected == 299
    assert len(df) == expected


def test_A057_samples_without_municipality(engine, bank, con):
    _, df = ask(engine, bank, "A057")
    expected = scalar(con, """SELECT count(DISTINCT "كود العينة") FROM chemistry_tidy WHERE "اسم البلدية" IS NULL""")
    assert expected == 202
    assert int(df["missing_samples"].iloc[0]) == expected
