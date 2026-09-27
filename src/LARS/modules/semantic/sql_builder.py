"""
ResolvedSpec -> parameterized, read-only SQL on chemistry_tidy.

Only the whitelisted column expressions below are ever written into the SQL
text; every value is a parameter. Ordering is deterministic (value, then a
name tie-breaker) and every query has a LIMIT.

Definitions
  non-compliant   sample_result = 'Non-Compliant' (the lab's official verdict)
  above limit     is_above_limit = 1: a result above the EU MRL, a technical
                  reference comparison, never called a violation
  rates           denominator = ALL distinct samples matching the filters,
                  including samples whose sample_result is empty (27 in the
                  demo DB: the 25 'NO DETECTION' samples + 2 without a verdict).
                  Same rule as the handlers: 240 / 1,859 = 12.9%.
  totals          a grouped answer's total row is recomputed over distinct
                  samples, never summed from the groups (a sample can sit
                  under two categories); share_pct is against that total.
  analytes        only raw names with a non-empty canonical name in
                  analyte_map.csv are analytes. Markers ('NO DETECTION',
                  'NO CBD', the 'University' spellings) map to '' and never
                  appear in lists, rankings, never_detected_list or filters.
  pesticide filter  a sample qualifies when the analyte was detected in it;
                  for above-limit metrics, when that analyte was above the limit
"""
from __future__ import annotations

from typing import List, Optional, Tuple

import duckdb
import pandas as pd

from modules.semantic.catalog import Catalog
from modules.semantic.query_spec import (
    ABOVE_LIMIT_METRICS, ANALYTE_METRICS, RATE_METRICS, GroupBy, Metric, Scope, Sort,
)
from modules.semantic.validator import ResolvedSpec, SpecRejected

FILTER_COLUMNS = {
    "categories": '"نوع العينة"',
    "products": '"اسم العينة"',
    "municipalities": '"اسم البلدية"',
    "neighborhoods": '"الحى"',
}
GROUP_EXPR = {
    GroupBy.category: '"نوع العينة"',
    GroupBy.product: '"اسم العينة"',
    GroupBy.municipality: '"اسم البلدية"',
    GroupBy.neighborhood: '"الحى"',
    GroupBy.month: "strftime(test_date, '%Y-%m')",
}
MAX_ROWS = 200
MIN_RATE_SAMPLES = 10       # same threshold as the engine's rate rankings

MAIN_COLUMN = {
    Metric.sample_count: "samples",
    Metric.noncompliant_count: "non_compliant",
    Metric.noncompliance_rate: "rate_pct",
    Metric.above_limit_sample_count: "above_limit_samples",
    Metric.above_limit_rate: "rate_pct",
}


def _in(col: str, values) -> Tuple[str, list]:
    return f"{col} IN ({', '.join('?' * len(values))})", list(values)


def base_where(r: ResolvedSpec) -> Tuple[str, list]:
    clauses, params = [], []
    for attr, col in FILTER_COLUMNS.items():
        values = getattr(r, attr)
        if values:
            c, p = _in(col, values)
            clauses.append(c); params += p
    if r.period:
        clauses.append("test_date BETWEEN ? AND ?"); params += list(r.period)
    if r.spec.scope is Scope.non_compliant:
        clauses.append("sample_result = ?"); params.append("Non-Compliant")
    return (" AND ".join(clauses) or "TRUE"), params


def _per_sample(r: ResolvedSpec, group: Optional[str]) -> Tuple[str, list]:
    """One row per (group, sample) with its verdict / above-limit / has-analyte flags."""
    where, params = base_where(r)
    above = "is_above_limit = 1"
    above_params: list = []
    if r.spec.mrl_multiple is not None:
        above += " AND exceedance_ratio >= ?"; above_params.append(r.spec.mrl_multiple)
    pest_cols, pest_params = "", []
    if r.pesticide_raw:
        c, p = _in("pesticide_name", r.pesticide_raw)
        pest_cols = f", MAX(CASE WHEN is_detected = 1 AND {c} THEN 1 ELSE 0 END) AS has_analyte"
        pest_params = p
        if r.spec.metric in ABOVE_LIMIT_METRICS:
            above += f" AND {c}"; above_params += p
    grp = group or "CAST(NULL AS VARCHAR)"
    sql = f"""SELECT {grp} AS grp, "كود العينة" AS code,
        MAX(CASE WHEN sample_result = ? THEN 1 ELSE 0 END) AS nc,
        MAX(CASE WHEN {above} THEN 1 ELSE 0 END) AS above{pest_cols}
      FROM chemistry_tidy WHERE {where} GROUP BY 1, 2"""
    return sql, ["Non-Compliant"] + above_params + pest_params + params


def _groups_cte(r: ResolvedSpec, group: Optional[str]) -> Tuple[str, list]:
    """WITH s (per sample), g (per group): samples, non_compliant, above_limit_samples."""
    inner, params = _per_sample(r, group)
    conds = (["has_analyte = 1"] if r.pesticide_raw else []) + (["grp IS NOT NULL", "grp != ''"] if group else [])
    where = f"WHERE {' AND '.join(conds)}" if conds else ""
    return (f"""WITH s AS ({inner}), g AS (
        SELECT grp, COUNT(*) AS samples, SUM(nc) AS non_compliant, SUM(above) AS above_limit_samples
        FROM s {where} GROUP BY grp)""", params)


def _sample_metric_sql(r: ResolvedSpec, group: Optional[str], limit: Optional[int]) -> Tuple[str, list]:
    cte, params = _groups_cte(r, group)
    m = r.spec.metric
    threshold = bool(group) and m in RATE_METRICS
    direction = "ASC" if r.spec.sort is Sort.asc else "DESC"
    order = "grp ASC" if r.spec.group_by is GroupBy.month else f"{MAIN_COLUMN[m]} {direction}, grp ASC"
    rate_num = "non_compliant" if m is Metric.noncompliance_rate else "above_limit_samples"
    sql = f"""{cte}
      SELECT grp, samples, non_compliant, above_limit_samples,
        ROUND(100.0 * {rate_num} / samples, 1) AS rate_pct
      FROM g WHERE samples >= ? ORDER BY {order} LIMIT ?"""
    return sql, params + [MIN_RATE_SAMPLES if threshold else 1, limit or MAX_ROWS]


def _groups_below_threshold(con, r: ResolvedSpec, group: str) -> int:
    cte, params = _groups_cte(r, group)
    return con.execute(f"{cte} SELECT COUNT(*) FROM g WHERE samples < ?", params + [MIN_RATE_SAMPLES]).fetchone()[0]


def _amap_values(catalog: Catalog) -> Tuple[str, list]:
    a = catalog.analytes
    pairs = sorted((raw, can, a.canonical_class[can]) for raw, can in a.raw_to_canonical.items() if can)
    return (", ".join("(?, ?, ?)" for _ in pairs), [x for p in pairs for x in p])


def _analyte_sql(r: ResolvedSpec, catalog: Catalog) -> Tuple[str, list]:
    values, v_params = _amap_values(catalog)
    where, w_params = base_where(r)
    m = r.spec.metric
    detected = f"""SELECT a.canonical, a.cls, t."كود العينة" AS code, COALESCE(MAX(t.is_above_limit), 0) AS above
        FROM chemistry_tidy t JOIN amap a ON t.pesticide_name = a.raw
        WHERE t.is_detected = 1 AND {{where}} GROUP BY 1, 2, 3"""
    head = f"WITH amap(raw, canonical, cls) AS (VALUES {values}), d AS ({detected.format(where=where)})"
    if m is Metric.never_detected_list:
        sql = f"""{head}, everywhere AS ({detected.format(where='TRUE')})
          SELECT canonical AS pesticide, cls AS analyte_class, COUNT(*) AS samples_detected_elsewhere
          FROM everywhere WHERE canonical NOT IN (SELECT canonical FROM d)
          GROUP BY 1, 2 ORDER BY pesticide ASC LIMIT ?"""
        return sql, v_params + w_params + [MAX_ROWS]
    limit = r.spec.top_n if m is Metric.top_pesticides else MAX_ROWS
    direction = "ASC" if (m is Metric.top_pesticides and r.spec.sort is Sort.asc) else "DESC"
    sql = f"""{head}
      SELECT canonical AS pesticide, cls AS analyte_class, COUNT(*) AS samples_detected,
             SUM(above) AS samples_above_limit
      FROM d GROUP BY 1, 2 ORDER BY samples_detected {direction}, pesticide ASC LIMIT ?"""
    return sql, v_params + w_params + [limit]


def _matching_samples(con, r: ResolvedSpec) -> int:
    cte, params = _groups_cte(r, None)
    return con.execute(f"{cte} SELECT COALESCE(SUM(samples), 0) FROM g", params).fetchone()[0]


class NoMatchingSamples(SpecRejected):
    pass


def run(r: ResolvedSpec, catalog: Catalog, db_path: str) -> Tuple[pd.DataFrame, Optional[pd.DataFrame], dict]:
    """Returns (result, total_row_or_None, info). Raises NoMatchingSamples."""
    m = r.spec.metric
    with duckdb.connect(str(db_path), read_only=True) as con:
        n = _matching_samples(con, r)
        if n == 0:
            raise NoMatchingSamples("matched no samples")
        info = {"matching_samples": n}
        if m in ANALYTE_METRICS:
            sql, params = _analyte_sql(r, catalog)
            return con.execute(sql, params).df(), None, {**info, "sql": sql}
        group = GROUP_EXPR.get(r.spec.group_by) if r.spec.group_by else None
        limit = r.spec.top_n if (group and "top_n" in r.spec.model_fields_set) else None
        sql, params = _sample_metric_sql(r, group, limit)
        df = con.execute(sql, params).df()
        total = None
        if group:
            total = con.execute(*_sample_metric_sql(r, None, None)).df()
            if m in RATE_METRICS:
                info["groups_below_threshold"] = _groups_below_threshold(con, r, group)
        return df, total, {**info, "sql": sql}
