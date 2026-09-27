"""
Catalog of the values that exist in chemistry_tidy, built once at startup.

The validator (Phase 2) resolves every QuerySpec filter against it, and the
LLM prompt (Phase 3) lists its vocabulary; the LLM never sees data rows.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Dict, Tuple

import duckdb

from modules.semantic.tables import AnalyteMap, load_analyte_map, load_category_map

SAMPLE = '"كود العينة"'


@dataclass(frozen=True)
class Catalog:
    categories: Dict[str, int]              # stored "نوع العينة" -> distinct samples
    products: Dict[str, int]                # "اسم العينة" -> distinct samples
    product_categories: Dict[str, Tuple[str, ...]]
    municipalities: Dict[str, int]
    neighborhoods: Dict[str, int]
    analytes: AnalyteMap
    category_terms: Dict[str, Tuple[str, ...]]  # normalized word -> stored categories
    min_date: date
    max_date: date
    total_samples: int


def _counts(con, column: str) -> Dict[str, int]:
    rows = con.execute(f"""SELECT {column}, COUNT(DISTINCT {SAMPLE}) FROM chemistry_tidy
        WHERE {column} IS NOT NULL AND trim({column}) != '' GROUP BY 1 ORDER BY 1""").fetchall()
    return dict(rows)


def build_catalog(db_path: str) -> Catalog:
    with duckdb.connect(str(db_path), read_only=True) as con:
        categories = _counts(con, '"نوع العينة"')
        product_categories = {p: tuple(c.split("|")) for p, c in con.execute(
            """SELECT "اسم العينة", string_agg(DISTINCT "نوع العينة", '|' ORDER BY "نوع العينة")
               FROM chemistry_tidy WHERE "اسم العينة" IS NOT NULL AND "نوع العينة" IS NOT NULL
               GROUP BY 1 ORDER BY 1""").fetchall()}
        catalog_raw = {r[0] for r in con.execute(
            "SELECT DISTINCT pesticide_name FROM chemistry_tidy WHERE pesticide_name IS NOT NULL").fetchall()}
        min_date, max_date, total = con.execute(
            f"SELECT MIN(test_date), MAX(test_date), COUNT(DISTINCT {SAMPLE}) FROM chemistry_tidy").fetchone()
        catalog = Catalog(
            categories=categories,
            products=_counts(con, '"اسم العينة"'),
            product_categories=product_categories,
            municipalities=_counts(con, '"اسم البلدية"'),
            neighborhoods=_counts(con, '"الحى"'),
            analytes=load_analyte_map(),
            category_terms=load_category_map(),
            min_date=min_date, max_date=max_date, total_samples=total,
        )
    _check_tables(catalog, catalog_raw)
    return catalog


def _check_tables(catalog: Catalog, raw_names: set) -> None:
    """Fail at startup rather than answer from a stale table."""
    unmapped = raw_names - set(catalog.analytes.raw_to_canonical)
    if unmapped:
        raise ValueError(f"analyte_map.csv is missing raw names: {sorted(unmapped)}")
    unknown = {v for vals in catalog.category_terms.values() for v in vals} - set(catalog.categories)
    if unknown:
        raise ValueError(f"category_map.csv names categories not in the DB: {sorted(unknown)}")
