"""
entity_detection.py — extracted from core_query_engine.py (2026-09-18, Phase 3 split).

Arabic-NLP entity layer: query normalization and detection of
sample types, neighborhoods and pesticides, plus the SQL sample
filter builder and the per-query context dict.
Methods are byte-identical to their pre-split versions; this module only
relocates them. EntityDetectionMixin is mixed into CoreQueryEngine — methods refer to
engine state (self._get_connection(), detection helpers, handlers) via self.
"""
from typing import List, Optional

from modules.query.mappings import CATEGORY_EN
from modules.query.text_norm import NormText, has_period_phrase, named_years, names_quarter


class EntityDetectionMixin:
    def _build_sample_filter(self, samples: list) -> str:
        """
        Build SQL WHERE clause for "اسم العينة".

        YOUR DATABASE stores ARABIC names ('طماطم', 'خيار', ...).
        _detect_sample_types() returns English canonical values ('Tomato').
        This method converts them back to Arabic substrings for the LIKE.

        Falls back to English substring search too, so the filter works
        even if the DB is later migrated to English names.
        """
        if not samples:
            return "1=1"

        # Normal path: exact match on product names the EntityResolver loaded
        # from the DB. The old LIKE fallbacks below also matched the category
        # column ("نوع العينة" LIKE '%Dates%'), so the product 'Dates' pulled in
        # the whole Dates category (Date Paste, Date Molasses, …). Only values
        # that exist in the DB are emitted, so no user text reaches the SQL;
        # none valid → '1=0' (no rows), never all data.
        resolver = self._get_resolver()
        if resolver is not None:
            valid = [s for s in samples if s in resolver.product_tokens]
            if not valid:
                return "1=0"
            values = ", ".join("'" + v.replace("'", "''") + "'" for v in valid)
            return f'"اسم العينة" IN ({values})'

        # Fallback only when the DB (and so the resolver) is unavailable.
        # Build reverse map: English canonical → list of Arabic query keys
        # e.g. 'Tomato' → ['طماطم', 'طماطم شيري']  (only the base match matters)
        from modules.query.mappings import SAMPLE_CORRECTIONS

        en_to_ar: dict = {}
        for ar_key, en_val in SAMPLE_CORRECTIONS.items():
            en_to_ar.setdefault(en_val, []).append(ar_key)

        conditions = []
        for s in samples:
            # ── A: Arabic LIKE (what your DB actually has) ──────────────
            arabic_variants = en_to_ar.get(s, [])
            # Use TRIM() on the column side to handle accidental spaces
            for ar in arabic_variants:
                conditions.append(
                    f"TRIM(\"اسم العينة\") LIKE '%{ar}%'"
                )

            # ── B: English LIKE fallback (future-proof) ─────────────────
            conditions.append(f"\"اسم العينة\" LIKE '%{s}%'")

            # ── C: Category column (نوع العينة) ─────────────────────────
            conditions.append(f"\"نوع العينة\" LIKE '%{s}%'")

        return f"({' OR '.join(conditions)})"

    def _normalize_query(self, query: str) -> str:
        """Normalize query: apply dialect synonyms for English."""
        query_lower = query.lower().strip()
        for dialect, standard in self.dialect_synonyms.items():
            query_lower = query_lower.replace(dialect, standard)
        return query_lower

    def _detect_sample_types(self, query: str) -> List[str]:
        """
        Detect sample types from query.
        DB stores ENGLISH names in "اسم العينة" (e.g. 'Tomato', 'Pistachios').
        Returns English DB values directly.

        With an EntityResolver (the normal case) these are exact DB values, or a
        single '__cat__<DB category>' sentinel when only a category was named.
        The dictionary scan below is the fallback when the DB is unavailable.
        """
        res = self._resolve(query)
        if res is not None:
            if res.products:
                return list(res.products)
            return [f"__cat__{res.categories[0]}"] if res.categories else []

        detected = []
        query_lower = query.lower()
        remaining_lower = query_lower  # track consumed text to avoid sub-matches

        from modules.query.mappings import SAMPLE_CORRECTIONS_NORM, normalize_arabic_text
        norm_query = normalize_arabic_text(query)
        remaining_norm = norm_query
        remaining_lower_en = query.lower()  # kept for English keys only

        # Arabic keys — normalized match
        for norm_key in sorted(SAMPLE_CORRECTIONS_NORM.keys(), key=len, reverse=True):
            if any('\u0600' <= c <= '\u06ff' for c in norm_key):
                if norm_key in remaining_norm:
                    detected.append(SAMPLE_CORRECTIONS_NORM[norm_key])
                    remaining_norm = remaining_norm.replace(norm_key, " " * len(norm_key), 1)

        # English keys — original .lower() substring match (unaffected by
        # the Arabic normalization gap, left as-is)
        for key in sorted(self.sample_types.keys(), key=len, reverse=True):
            if not any('\u0600' <= c <= '\u06ff' for c in key):
                db_value = self.sample_types[key]
                if key in remaining_lower_en:
                    detected.append(db_value)
                    remaining_lower_en = remaining_lower_en.replace(key, " " * len(key), 1)

        # Category expansion — uses English "نوع العينة" values from DB
        # CATEGORY_EN imported from modules.query.mappings — single source of truth
        if not detected:
            matched_cat = None
            for kw, cat in CATEGORY_EN.items():
                if kw in query_lower:
                    matched_cat = cat
                    break
            if matched_cat:
                # Return a special sentinel so process() knows it's a category
                detected = [f"__cat__{matched_cat}"]

        return sorted(set(detected))

    def _detect_neighborhoods(self, query: str) -> List[str]:
        """
        Detect neighborhood names. DB stores Arabic values (الإسكان, الريان etc.)
        Supports English transliterations and Arabic matching.
        """
        res = self._resolve(query)
        if res is not None:
            # Product qualifiers ('الفلفل الأخضر') are consumed by the resolver and
            # must not be read as the neighborhood of the same name.
            query = self._get_resolver().mask_consumed(query, res)
        detected = []
        query_lower = query.lower()

        # Sort by length descending
        for key in sorted(self.neighborhood_patterns.keys(), key=len, reverse=True):
            db_val = self.neighborhood_patterns[key]
            # Arabic strings are checked against exact query, English against lower
            has_arabic = any('\u0600' <= c <= '\u06ff' for c in key)
            if has_arabic:
                if key in query:
                    detected.append(db_val)
            else:
                if key in query_lower:
                    detected.append(db_val)

        # Sorted, not list(set(...)): set order changes with PYTHONHASHSEED and
        # this list is shown in answers and used to build filters.
        return sorted(set(detected))

    def _detect_pesticide(self, query: str) -> Optional[str]:
        """Pesticide named in the query — see mappings.detect_pesticide, shared
        with IntentRouter._extract_pesticide so both tiers agree."""
        from modules.query.mappings import detect_pesticide
        return detect_pesticide(query)

    def _extract_context(self, query: str) -> dict:
        """
        Normalize the query and detect all entities (samples, neighborhoods, pesticide, period).

        Strips category sentinels (__cat__<key>) from detected_samples so that
        standard handlers always receive concrete sample names. The sentinel is
        preserved separately as 'category_key' for handlers that need it (e.g.
        Pattern 1B / violations-threshold).

        Returns a context dict consumed by process() routing tiers.

        query / query_normalized / query_lower are NormText: the original text,
        but `kw in query` compares normalized forms (text_norm.norm), so every
        tier matches "غير المطابقه", "اداء", "أيٍّ" the same way as the
        canonical spelling.
        """
        query = NormText(query)
        query_normalized = NormText(self._normalize_query(query))
        query_lower = NormText(query_normalized.lower())

        detected_samples_raw = self._detect_sample_types(query)
        detected_neighborhoods = self._detect_neighborhoods(query)
        detected_pesticide = self._detect_pesticide(query)
        relative_period = self._detect_time_period(query)
        detected_period = relative_period
        if detected_period is None:
            detected_period = self._detect_absolute_month(query)
        detected_period_label = self._period_label(query) if detected_period else None
        category_key = None
        detected_samples = []
        for s in detected_samples_raw:
            if s.startswith("__cat__"):
                category_key = s.replace("__cat__", "")
            else:
                detected_samples.append(s)

        return {
            'query': query,
            'query_normalized': query_normalized,
            'query_lower': query_lower,
            'detected_samples': detected_samples,
            'detected_samples_raw': detected_samples_raw,
            'detected_neighborhoods': detected_neighborhoods,
            'detected_pesticide': detected_pesticide,
            'detected_period': detected_period,
            'detected_period_label': detected_period_label,
            'category_key': category_key,
            'resolution': self._resolve(query),
            # A relative-period phrase ("خلال الأشهر الأخيرة") that did not parse:
            # answering over all dates would silently broaden the question.
            'period_unresolved': detected_period is None and has_period_phrase(query),
            # "من يناير إلى مارس": month ranges are not supported yet; refused.
            'multi_month': len(self._months_mentioned(query)) >= 2,
            # A year the month filter cannot honour: refused.
            'period_unhandled': self._period_unhandled(query, relative_period, detected_period),
            # "الربع الأول": no handler filters by a quarter; only a quarterly
            # breakdown may answer (CoreQueryEngine._quarter_grouped).
            'quarter_named': names_quarter(query),
        }

    def _period_unhandled(self, query: str, relative_period: Optional[str],
                          detected_period: Optional[str]) -> bool:
        """True when the question names a year the handlers cannot filter by:
        their month filter ignores the year, so a named year is kept only for a
        single month in the one year the data covers ("مارس 2026" while the
        data is all 2026)."""
        years = named_years(query)
        if not years:
            return False
        month_only = relative_period is None and detected_period is not None
        return not (month_only and years == self._data_years() and len(years) == 1)

    def _data_years(self) -> List[int]:
        """Calendar years present in chemistry_tidy (cached per engine)."""
        return self._data_dates()[0]

    def _data_max_date(self):
        """MAX(test_date) (cached per engine)."""
        return self._data_dates()[1]

    def _data_dates(self):
        if getattr(self, "_data_dates_cache", None) is None:
            con = self._get_connection()
            try:
                years = [int(y) for (y,) in con.execute(
                    "SELECT DISTINCT year(test_date) FROM chemistry_tidy "
                    "WHERE test_date IS NOT NULL ORDER BY 1").fetchall()]
                max_date = con.execute("SELECT MAX(test_date) FROM chemistry_tidy").fetchone()[0]
            finally:
                con.close()
            self._data_dates_cache = (years, max_date)
        return self._data_dates_cache
