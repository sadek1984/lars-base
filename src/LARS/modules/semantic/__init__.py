"""
Semantic fallback layer.

Runs only after the deterministic engine refuses. An LLM fills a structured
QuerySpec (never SQL, never sees data rows); the spec is validated against
the catalog of values that exist in the DB, then turned into parameterized,
read-only SQL.

Phase 1 (this package so far): the catalog, the reviewed category and
analyte tables, the QuerySpec schema and the period definitions.
"""
