"""
Batch 4 — root causes found by the consistency (paraphrase) test:
never silently broaden, one shared normalization, compliance verb forms,
the legacy product-filter leak, number words only for count nouns, and the
EU MRL wording for the technical metric.

Expected values are recomputed with independent SQL against
lars_data_demo.duckdb (read-only).

Run:  pytest tests/test_batch4.py -v
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

PEPPER = """"اسم العينة" ILIKE '%pepper%'"""
RAW_DATES = "('Dates','Khlas Dates','Saqai Dates','Sukari Dates','Wanana Dates')"
TOMATO = "('Tomato','Cherry Tomato','Cluster Tomato')"
LAST_3_MONTHS = """strptime("التاريخ", '%d/%m/%Y') >=
    (SELECT MAX(strptime("التاريخ", '%d/%m/%Y')) FROM chemistry_tidy) - INTERVAL 3 month"""


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


def one(con, sql):
    return con.execute(sql).fetchone()


# ── 1. Never silently broaden ────────────────────────────────────────────────

def test_misheard_product_gets_honest_not_found_with_suggestion(engine):
    text, df = engine.process("ما هي عينات الفلافل الراسبه؟")[:2]
    assert df is None
    assert "لم أجد" in text and "الفلافل" in text and "فلفل" in text
    assert "1859" not in text and "All types" not in text


def test_period_phrase_after_unit_sets_the_period(engine, con):
    """B042 msa: 'خلال الأشهر الثلاثة الأخيرة' was dropped (206 all-time)."""
    _, df = engine.process("ما عدد عينات الطماطم الراسبة خلال الأشهر الثلاثة الأخيرة؟")[:2]
    samples, nc = one(con, f"""SELECT COUNT(DISTINCT "كود العينة"),
        COUNT(DISTINCT CASE WHEN sample_result = 'Non-Compliant' THEN "كود العينة" END)
        FROM chemistry_tidy WHERE "اسم العينة" IN {TOMATO} AND {LAST_3_MONTHS}""")
    assert int(df["sample_count"].sum()) == samples
    assert int(df["non_compliant"].sum()) == nc


def test_unparseable_period_is_not_answered_over_all_data(engine):
    text, df = engine.process("ما عدد عينات الطماطم الراسبة خلال الأشهر الأخيرة؟")[:2]
    assert df is None and "الفترة الزمنية" in text


# ── 2. Shared normalization + fuzzy pesticide in both layers ─────────────────

def test_normalized_matching():
    from modules.query.text_norm import NormText, norm
    assert "غير مطابقة" in NormText("العينات غير مطابقه")
    assert "أداء" in NormText("ما هو اداء كل بلديه")
    assert "في أي" in NormText("في أيٍّ من التوابل")
    assert norm("إبريل") == norm("أبريل") == norm("ابريل")


def test_both_extraction_layers_resolve_misheard_pesticide(engine):
    q = "قارن متوسط تركيز الكاربندازين بين التوابل والخضراوات"
    assert engine._extract_context(q)["detected_pesticide"] == "carbendazim"
    assert engine.router.analyze(q)[1].pesticide == "carbendazim"


def test_E016_misheard_name_gives_same_answer_as_original(engine, bank):
    _, original = engine.process(bank["E016"])[:2]
    _, variant = engine.process("قارن متوسط تركيز الكاربندازين بين التوابل والخضراوات")[:2]
    assert variant.to_csv(index=False) == original.to_csv(index=False)


# ── 3. Compliance verb forms → official verdict ──────────────────────────────

def test_dialect_rasabat_routes_to_compliance(engine, con):
    _, df = engine.process("وش عينات الفلفل اللي رسبت؟")[:2]
    nc = one(con, f"""SELECT COUNT(DISTINCT "كود العينة") FROM chemistry_tidy
        WHERE {PEPPER} AND sample_result = 'Non-Compliant'""")[0]
    assert int(df["non_compliant"].sum()) == nc == 29


@pytest.mark.parametrize("q", [
    "وش العينات اللي ما طابقت في جمعية البطين الزراعية؟",
    "ما هي العينات غير المطابقه في جمعيه البطين الزراعيه",
])
def test_negated_match_verb_and_ha_spelling_route_to_compliance(engine, con, q):
    _, df = engine.process(q)[:2]
    nc = one(con, """SELECT COUNT(DISTINCT "كود العينة") FROM chemistry_tidy
        WHERE "اسم البلدية" = 'جمعية البطين الزراعية' AND sample_result = 'Non-Compliant'""")[0]
    assert int(df["non_compliant"].sum()) == nc == 7


def test_compliance_vocabulary():
    from modules.query.text_norm import compliance_intent as ci
    assert ci("رسبت") == ci("رسب") == ci("ما طابقت") == ci("ما طابق") == "non_compliant"
    assert ci("طابقت") == ci("نجحت") == "compliant"
    assert ci("كم مطابقة وكم غير مطابقة") == "non_compliant"
    assert ci("نسبة الرسوب") is None and ci("العينات المخالفه") is None


# ── 4. Legacy product filter no longer leaks the Dates category ──────────────

def test_X01_raw_dates_pesticides(engine, con):
    _, df = engine.process("ما هي المبيدات التي ظهرت في التمور؟")[:2]
    expected = sorted(r[0] for r in con.execute(f"""SELECT DISTINCT pesticide_name FROM chemistry_tidy
        WHERE is_detected = 1 AND pesticide_name NOT IN ('NO DETECTION','NO DATA')
          AND "اسم العينة" IN {RAW_DATES}""").fetchall())
    assert expected == ["abamectin", "cypermethrin", "fenpyroximate", "imidacloprid"]
    assert sorted(df["pesticide"]) == expected


# ── 5. Number words only when they quantify a count noun ─────────────────────

@pytest.mark.parametrize("q", ["وش أخطر خمس أحياء من ناحية نسبة المخالفة؟",
                               "ما هي أخطر خمسة أحياء من حيث نسبة المخالفة؟"])
def test_spoken_number_sets_top_n(engine, q):
    _, df = engine.process(q)[:2]
    assert len(df) == 5


def test_safe_limit_al_wahid_is_not_a_pesticide_count(engine, bank):
    _, original = engine.process(bank["E035"])[:2]
    _, variant = engine.process(
        "ما هو متوسط عدد المبيدات في العينات التي تجاوز مؤشر خطرها الحد الآمن الواحد؟")[:2]
    assert variant.to_csv(index=False) == original.to_csv(index=False)


def test_marra_wahida_is_not_a_pesticide_count(engine, con):
    _, df = engine.process("ما هي كل المبيدات التي ظهرت ولو مرة واحدة في التمور؟")[:2]
    assert "pesticide" in df.columns and len(df) == 4


def test_count_for_nouns():
    from modules.query.text_norm import count_for_nouns, parse_period
    assert count_for_nouns("الأحياء الخمسة") == [5]
    assert count_for_nouns("الحد الآمن الواحد") == [] == count_for_nouns("ولو مرة واحدة")
    assert count_for_nouns("تحتوي على ١ مبيد و٢ مبيد") == [1, 2]
    assert parse_period("آخر ثلاث شهور") == parse_period("الأشهر الثلاثة الأخيرة") == (3, "month")


# ── 6. EU MRL wording for the technical metric ───────────────────────────────

def test_rate_answers_use_eu_mrl_wording(engine, bank):
    for qid in ("D010", "D011", "D012", "D019"):
        text = engine.process(bank[qid])[0]
        assert "الحد الأقصى الأوروبي" in text, qid
        assert "نسبة المخالفة" not in text and "Above limit" not in text, qid


# ── Knock-on fixes found in the harness review ───────────────────────────────

@pytest.mark.parametrize("qid, pattern", [("B001", "bifenth%"), ("B004", "buprof%")])
def test_non_compliant_with_named_pesticide_keeps_the_pesticide(engine, bank, con, qid, pattern):
    _, df = engine.process(bank[qid])[:2]
    nc = one(con, f"""SELECT COUNT(DISTINCT "كود العينة") FROM chemistry_tidy WHERE is_detected = 1
        AND lower(pesticide_name) LIKE '{pattern}' AND "اسم العينة" IN {TOMATO}
        AND sample_result = 'Non-Compliant'""")[0]
    got = 0 if df is None or df.empty else df["sample_code"].nunique()
    assert got == nc


def test_B016_multiplier_applies_to_the_named_pesticide(engine, bank, con):
    text, df = engine.process(bank["B016"])[:2]
    n = one(con, f"""SELECT COUNT(*) FROM chemistry_tidy WHERE is_detected = 1 AND limit_value > 0
        AND lower(pesticide_name) LIKE 'buprof%' AND "اسم العينة" IN {TOMATO} AND exceedance_ratio >= 2""")[0]
    assert n == 0 and (df is None or len(df) == 0) and "buprofezin" in text


def test_C002_number_word_counted_once():
    from modules.query.text_norm import count_for_nouns
    assert count_for_nouns("ما عدد العينات التي تحتوي على مبيد واحد و٢ مبيد كل على حده؟") == [1, 2]


# ── Batch 4.1 ────────────────────────────────────────────────────────────────

def test_rawasib_means_residues_not_a_verdict(engine):
    from modules.query.text_norm import compliance_intent
    q = "ما هي رواسب المبيدات في الطماطم"
    assert compliance_intent(q) is None
    text = engine.process(q)[0]
    assert "Non-Compliant samples" not in text and "غير مطابقة" not in text


@pytest.mark.parametrize("q, month", [
    ("كم عينة مخالفة في مارس", 3),
    ("خلال شهر مارس", 3),
    ("العينات في شهر أبريل", 4),
])
def test_absolute_month_applies_and_is_not_refused(engine, q, month):
    ctx = engine._extract_context(q)
    assert f"= {month}" in (ctx["detected_period"] or "")
    assert ctx["period_unresolved"] is False
    assert "الفترة الزمنية" not in engine.process(q)[0]


def test_even_one_sample_sets_no_count(engine):
    from modules.query.text_norm import count_for_nouns
    q = "هل توجد ولو عينة واحدة مخالفة"
    assert count_for_nouns(q) == []
    assert engine.router.analyze(q)[1].n_pesticides is None
    assert engine._top_n(q) is None


@pytest.mark.parametrize("q", [
    "مين أعلى بلدية في نسبة المخالفة، شرق بريدة ولا غرب بريدة؟",
    "أي بلدية أعلى في نسبة المخالفة: بلدية شرق بريدة أو بلدية غرب بريدة؟",
])
def test_two_municipalities_without_qaarin_are_compared(engine, bank, q):
    _, original = engine.process(bank["D012"])[:2]
    _, df = engine.process(q)[:2]
    assert df.to_csv(index=False) == original.to_csv(index=False)
