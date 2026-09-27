"""
Semantic layer, Phase 2: validator, SQL builder, Arabic answer.

Hand-written QuerySpecs (no LLM) are answered and compared with independent
SQL written separately against lars_data_demo.duckdb (read-only). The
analyte-level expectations map raw names to canonical names in Python from
config/analyte_map.csv, not through the builder's SQL join.

Run:  pytest tests/test_semantic_phase2.py -v
"""
import csv
import sys
from collections import defaultdict
from pathlib import Path

import duckdb
import pytest

REPO = Path(__file__).resolve().parents[1]
LARS = REPO / "src" / "LARS"
DB_PATH = LARS / "data" / "lars_data_demo.duckdb"
sys.path.insert(0, str(LARS))

pytestmark = pytest.mark.skipif(not DB_PATH.exists(), reason="lars_data_demo.duckdb not present")

from modules.semantic.query_spec import QuerySpec  # noqa: E402

CODE = '"كود العينة"'
NC = "sample_result = 'Non-Compliant'"


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect(str(DB_PATH), read_only=True)
    yield c
    c.close()


@pytest.fixture(scope="module")
def ask():
    from modules.query.entity_resolver import EntityResolver
    from modules.semantic.answer import answer_spec
    from modules.semantic.catalog import build_catalog
    catalog = build_catalog(str(DB_PATH))
    with duckdb.connect(str(DB_PATH), read_only=True) as c:
        resolver = EntityResolver(c)
    return lambda spec: answer_spec(QuerySpec.model_validate(spec), catalog, resolver, str(DB_PATH))


@pytest.fixture(scope="module")
def amap():
    with (LARS / "config" / "analyte_map.csv").open(encoding="utf-8") as f:
        return {r["raw_name"]: r["canonical_name"] for r in csv.DictReader(f)}


def one(con, sql, params=()):
    return con.execute(sql, list(params)).fetchone()


def canonical_counts(con, amap, where):
    """canonical -> set of samples with a detection, mapped in Python."""
    out = defaultdict(set)
    for raw, code in con.execute(f"""SELECT pesticide_name, {CODE} FROM chemistry_tidy
            WHERE is_detected = 1 AND {where}""").fetchall():
        if amap.get(raw):
            out[amap[raw]].add(code)
    return out


def row(df, col, value):
    return df[df[col] == value].iloc[0]


# ── Failure-set questions (the 8 kept refusals) ──────────────────────────────

def test_B049_official_rate_spices_vs_overall(ask, con):
    a = ask({"metric": "noncompliance_rate", "group_by": "category"})
    nc, n = one(con, f"""SELECT COUNT(DISTINCT CASE WHEN {NC} THEN {CODE} END), COUNT(DISTINCT {CODE})
        FROM chemistry_tidy WHERE "نوع العينة" = 'Spices'""")
    all_nc, all_n = one(con, f"SELECT COUNT(DISTINCT CASE WHEN {NC} THEN {CODE} END), COUNT(DISTINCT {CODE}) FROM chemistry_tidy")
    assert (nc, n, all_nc, all_n) == (181, 479, 240, 1859)
    spices, total = row(a.df, "category", "Spices"), row(a.df, "category", "الإجمالي")
    assert (spices.non_compliant, spices.samples, spices.rate_pct) == (181, 479, 37.8)
    assert (total.non_compliant, total.samples, total.rate_pct) == (240, 1859, 12.9)
    assert "37.8%" in a.text and "12.9%" in a.text and "حسب تصنيف المختبر" in a.text


def test_B023_official_noncompliant_vegetables_vs_fruits(ask, con):
    a = ask({"metric": "noncompliant_count", "filters": {"category": ["الخضروات", "الفواكه"]}, "group_by": "category"})
    exp = dict(con.execute(f"""SELECT "نوع العينة", COUNT(DISTINCT {CODE}) FROM chemistry_tidy
        WHERE {NC} AND "نوع العينة" IN ('Vegetables', 'Fruits') GROUP BY 1""").fetchall())
    assert exp == {"Vegetables": 37, "Fruits": 11}
    assert {c: row(a.df, "category", c).non_compliant for c in exp} == exp
    assert "مخالف" not in a.text


def test_D023_spices_share_of_all_noncompliant(ask):
    a = ask({"metric": "noncompliant_count", "group_by": "category"})
    s = row(a.df, "category", "Spices")
    assert (s.non_compliant, s.share_pct) == (181, round(100 * 181 / 240, 1)) == (181, 75.4)


def test_B019_distinct_spice_samples_above_2x_mrl_no_limit_cut(ask, con):
    a = ask({"metric": "above_limit_sample_count", "filters": {"category": ["التوابل"]}, "mrl_multiple": 2})
    n = one(con, f"""SELECT COUNT(*) FROM (SELECT DISTINCT {CODE} FROM chemistry_tidy
        WHERE "نوع العينة" = 'Spices' AND limit_value > 0 AND concentration / limit_value >= 2)""")[0]
    assert n == 228 and a.df["above_limit_samples"].iloc[0] == n
    assert "الحد الأقصى الأوروبي" in a.text and "مخالف" not in a.text


def test_A025_pesticides_in_nuts(ask, con, amap):
    a = ask({"metric": "pesticide_list", "filters": {"category": ["المكسرات"]}})
    exp = canonical_counts(con, amap, """"نوع العينة" = 'Nuts'""")
    assert {p: n for p, n in zip(a.df["pesticide"], a.df["samples_detected"])} == {p: len(s) for p, s in exp.items()}
    assert "aflatoxin B1" in set(a.df["pesticide"])          # mycotoxins counted with pesticides


@pytest.mark.parametrize("qid, category, word, n", [("A038", "Spices", "التوابل", 10), ("A039", "Vegetables", "الخضروات", 5)])
def test_A038_A039_top_pesticides_in_a_category(ask, con, amap, qid, category, word, n):
    a = ask({"metric": "top_pesticides", "filters": {"category": [word]}, "top_n": n})
    exp = canonical_counts(con, amap, f""""نوع العينة" = '{category}'""")
    ranked = sorted(exp.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:n]
    assert list(zip(a.df["pesticide"], a.df["samples_detected"])) == [(p, len(s)) for p, s in ranked]


def test_A040_never_detected_in_fruits_uses_canonical_names(ask, con, amap):
    a = ask({"metric": "never_detected_list", "filters": {"category": ["الفواكه"]}})
    everywhere = canonical_counts(con, amap, "TRUE")
    fruits = canonical_counts(con, amap, """"نوع العينة" = 'Fruits'""")
    assert list(a.df["pesticide"]) == sorted(set(everywhere) - set(fruits))
    assert "acetamiprid" not in set(a.df["pesticide"])
    assert not set(a.df["pesticide"]) & {"acatamiprid", "accetamiprid", "aetamiprid"}


# ── Other metrics, filters, groupings ────────────────────────────────────────

def test_relative_and_range_periods(ask):
    assert ask({"metric": "sample_count", "period": {"type": "relative", "n": 3, "unit": "month"}}).df["samples"].iloc[0] == 1149
    assert ask({"metric": "sample_count", "period": {"type": "range", "start": "2026-01-01", "end": "2026-03-31"}}).df["samples"].iloc[0] == 1111


def test_absolute_month_noncompliant(ask, con):
    a = ask({"metric": "noncompliant_count", "period": {"type": "absolute_month", "month": 3}})
    exp = one(con, f"""SELECT COUNT(DISTINCT {CODE}) FROM chemistry_tidy WHERE {NC}
        AND strftime(strptime("التاريخ", '%d/%m/%Y'), '%Y-%m') = '2026-03'""")[0]
    assert a.df["non_compliant"].iloc[0] == exp
    assert "مارس 2026" in a.text


def test_A023_style_pesticide_filter_by_product(ask, con):
    a = ask({"metric": "noncompliant_count", "filters": {"category": ["التوابل"], "pesticide": ["الكاربندازيم"]},
             "group_by": "product"})
    exp = con.execute(f"""SELECT "اسم العينة", COUNT(DISTINCT {CODE}),
            COUNT(DISTINCT CASE WHEN {NC} THEN {CODE} END) FROM chemistry_tidy
        WHERE "نوع العينة" = 'Spices' AND is_detected = 1 AND lower(pesticide_name) LIKE 'carb%'
          AND lower(pesticide_name) NOT LIKE 'carbo%' AND pesticide_name != 'carbaryl'
        GROUP BY 1 ORDER BY 3 DESC, 1""").fetchall()
    got = [tuple(x) for x in a.df[a.df["product"] != "الإجمالي"][["product", "samples", "non_compliant"]].itertuples(index=False)]
    assert got == exp
    # 135 at the tag (carbendazim only) + 1 Cumin sample spelled 'carbemdazim'
    assert row(a.df, "product", "Cumin").samples == 136


def test_A046_style_neighborhood_and_category(ask, con):
    a = ask({"metric": "sample_count", "filters": {"category": ["التوابل"], "neighborhood": ["حي الإسكان"]},
             "group_by": "product"})
    exp = con.execute(f"""SELECT "اسم العينة", COUNT(DISTINCT {CODE}) FROM chemistry_tidy
        WHERE "نوع العينة" = 'Spices' AND "الحى" = 'الإسكان' GROUP BY 1 ORDER BY 2 DESC, 1""").fetchall()
    got = [tuple(x) for x in a.df[a.df["product"] != "الإجمالي"][["product", "samples"]].itertuples(index=False)]
    assert got == exp and exp[0] == ("Cumin", 9)


def test_above_limit_rate_per_municipality_matches_D011_definition(ask, con):
    a = ask({"metric": "above_limit_rate", "group_by": "municipality"})
    exp = con.execute(f"""SELECT "اسم البلدية", COUNT(DISTINCT {CODE}) AS n,
            COUNT(DISTINCT CASE WHEN is_above_limit = 1 THEN {CODE} END),
            ROUND(100.0 * COUNT(DISTINCT CASE WHEN is_above_limit = 1 THEN {CODE} END) / COUNT(DISTINCT {CODE}), 1) AS r
        FROM chemistry_tidy WHERE "اسم البلدية" IS NOT NULL GROUP BY 1 HAVING n >= 10 ORDER BY r DESC, 1""").fetchall()
    body = a.df[a.df["municipality"] != "الإجمالي"]
    assert [tuple(x) for x in body[["municipality", "samples", "above_limit_samples", "rate_pct"]].itertuples(index=False)] == exp
    assert "مخالف" not in a.text and "EU MRL" in a.text


def test_monthly_trend_is_chronological(ask, con):
    a = ask({"metric": "noncompliance_rate", "group_by": "month"})
    exp = con.execute(f"""SELECT strftime(test_date, '%Y-%m') m, COUNT(DISTINCT {CODE}),
            COUNT(DISTINCT CASE WHEN {NC} THEN {CODE} END) FROM chemistry_tidy
        WHERE test_date IS NOT NULL GROUP BY 1 ORDER BY 1""").fetchall()
    body = a.df[a.df["month"] != "الإجمالي"]
    assert row(a.df, "month", "الإجمالي").samples == 1859      # the 5 undated samples count in the total only
    assert [tuple(x) for x in body[["month", "samples", "non_compliant"]].itertuples(index=False)] == exp


def test_top_pesticides_in_noncompliant_tomatoes(ask, con, amap):
    a = ask({"metric": "top_pesticides", "scope": "non_compliant", "filters": {"product": ["الطماطم"]}})
    exp = canonical_counts(con, amap, f""""اسم العينة" IN ('Tomato', 'Cherry Tomato', 'Cluster Tomato') AND {NC}""")
    ranked = sorted(exp.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:5]
    assert list(zip(a.df["pesticide"], a.df["samples_detected"])) == [(p, len(s)) for p, s in ranked]


def test_category_word_given_as_product_means_the_category(ask):
    a = ask({"metric": "sample_count", "filters": {"product": ["المكسرات"]}})
    assert a.df["samples"].iloc[0] == 151 and "حسب تصنيف المختبر" in a.text


def test_grouped_rows_are_not_cut_unless_top_n_is_asked(ask):
    assert len(ask({"metric": "sample_count", "group_by": "product"}).df) == 108 + 1
    assert len(ask({"metric": "sample_count", "group_by": "product", "top_n": 3}).df) == 3 + 1


# ── Refusals ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("spec, needle", [
    ({"metric": "sample_count", "filters": {"product": ["الفلافل"]}}, "«الفلافل»"),
    ({"metric": "sample_count", "filters": {"category": ["الحلويات"]}}, "«الحلويات»"),
    ({"metric": "sample_count", "filters": {"pesticide": ["المايونيز"]}}, "«المايونيز»"),
    ({"metric": "sample_count", "filters": {"municipality": ["بلدية جدة"]}}, "«بلدية جدة»"),
    ({"metric": "sample_count", "filters": {"neighborhood": ["حي النخيل الغربي"]}}, "«حي النخيل الغربي»"),
    ({"metric": "sample_count", "unsupported": True, "reason": "السؤال عن الأسعار"}, "الأسعار"),
    ({"metric": "noncompliance_rate", "scope": "non_compliant"}, "غير المطابقة فقط"),
    ({"metric": "sample_count", "period": {"type": "absolute_month", "month": 9}}, "خارج نطاق"),
    ({"metric": "sample_count", "filters": {"product": ["الطماطم"], "neighborhood": ["الإسكان"]},
      "period": {"type": "absolute_month", "month": 5}}, "لم تطابق أي عينة"),
])
def test_refusals_name_the_problem(ask, spec, needle):
    a = ask(spec)
    assert not a.ok and a.df is None and needle in a.text


# ── Contract ─────────────────────────────────────────────────────────────────

CONTRACT_SPECS = [
    {"metric": "sample_count"},
    {"metric": "noncompliance_rate", "filters": {"category": ["التوابل"]}},
    {"metric": "above_limit_rate", "group_by": "neighborhood", "top_n": 5},
    {"metric": "top_pesticides", "filters": {"municipality": ["شرق بريدة"]}},
]


@pytest.mark.parametrize("spec", CONTRACT_SPECS)
def test_answer_contract(ask, spec):
    a = ask(spec)
    assert a.ok and a.text.startswith("فهمت سؤالك كالتالي: ")
    assert ("حسب تصنيف المختبر" in a.text) == bool(spec.get("filters", {}).get("category"))
    assert "مخالف" not in a.text
    # values are parameters, never SQL text
    for words in spec.get("filters", {}).values():
        for w in words:
            assert w not in a.info["sql"]
    assert "Spices" not in a.info["sql"] and "LIMIT ?" in a.info["sql"]
    b = ask(spec)
    assert (a.text, a.df.to_csv(index=False)) == (b.text, b.df.to_csv(index=False))


def test_connection_is_read_only(monkeypatch, ask):
    import modules.semantic.sql_builder as sb
    seen = []
    real = sb.duckdb.connect
    monkeypatch.setattr(sb.duckdb, "connect", lambda *a, **k: seen.append(k.get("read_only")) or real(*a, **k))
    ask({"metric": "sample_count"})
    assert seen and all(seen)
