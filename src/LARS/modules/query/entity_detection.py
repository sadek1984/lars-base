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

        return list(set(detected))

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

        return list(set(detected))

    def _detect_pesticide(self, query: str) -> Optional[str]:
        """
        كشف المبيد — Arabic-first, English fallback.

        BUGFIX: the original version only checked whether the English
        canonical name appeared literally in the query text — which
        only ever matches Latin-script mentions embedded in an Arabic
        sentence (e.g. "ابحث عن bifenthrin"). Pure-Arabic pesticide
        names like "الإيميداكلوبرايد" never matched here even though
        the exact same string correctly resolves via
        IntentRouter._extract_pesticide()'s PESTICIDE_AR_TO_EN lookup.
        Since this method feeds ctx['detected_pesticide'] — shared by
        Tier 0, the semantic tier, and Tier 3 — that gap silently
        broke every Arabic-only pesticide query that Tier 2 didn't
        already classify into a pesticide-carrying intent.

        Order:
          1. Arabic key match against self.arabic_pesticide_map
             (== PESTICIDE_AR_TO_EN), longest key first so e.g.
             "الأيميداكلوبريد" doesn't get shadowed by a shorter
             partial key.
          2. English canonical name literal match (Latin-script
             mentions mid-Arabic-sentence, e.g. "bifenthrin").
          3. Common-name fallback list (English), for names that
             might be missing from PESTICIDE_AR_TO_EN's keys.
        """
        # 1. Arabic — normalized match (handles hamza/ta-marbuta/ال-prefix
        # spelling variants). Longest keys first to avoid short-prefix
        # shadowing, e.g. matching "بابروفيزن" before a shorter substring
        # of a different pesticide name.
        from modules.query.mappings import (
            PESTICIDE_AR_TO_EN_NORM,
            PESTICIDE_AR_TO_EN_NORM_NOSPACE,
            normalize_arabic_text,
        )
        norm_query = normalize_arabic_text(query)
        for norm_key in sorted(PESTICIDE_AR_TO_EN_NORM.keys(), key=len, reverse=True):
            if norm_key in norm_query:
                return PESTICIDE_AR_TO_EN_NORM[norm_key]

        # 1c. Fuzzy phonetic fallback — catches ASR letter insertions/drops
        # that exact and space-insensitive matching above miss (see
        # fuzzy_match_pesticide_ar's docstring for why this is necessary
        # rather than another dictionary entry).
        # Generic words ("المبيدات", "السموم الفطرية") are removed first: on their
        # own they fuzzy-score >= 82 against 'اللامبدا' and used to inject
        # lambda-cyhalothrin into questions that name no pesticide at all.
        from modules.query.mappings import fuzzy_match_pesticide_ar, strip_generic_pesticide_words
        _nospace_for_fuzzy = strip_generic_pesticide_words(norm_query).replace(" ", "")
        fuzzy_result = fuzzy_match_pesticide_ar(_nospace_for_fuzzy) if _nospace_for_fuzzy else None
        if fuzzy_result:
            return fuzzy_result
        # 1b. Arabic — space-insensitive fallback for compound transliterated
        # names (e.g. "الأزوكسي ستروبين" vs dict's "الازوكسيستروبين").
        # Scoped to pesticide names only — see mappings.py for rationale.
        nospace_query = norm_query.replace(" ", "")
        for norm_key in sorted(PESTICIDE_AR_TO_EN_NORM_NOSPACE.keys(), key=len, reverse=True):
            if norm_key in nospace_query:
                return PESTICIDE_AR_TO_EN_NORM_NOSPACE[norm_key]

        # 2. English canonical values, literal substring match
        query_lower = query.lower()
        unique_en_pesticides = sorted(
            set(self.arabic_pesticide_map.values()), key=len, reverse=True
        )
        for en_name in unique_en_pesticides:
            if en_name.lower() in query_lower:
                return en_name

        # 3. Common-name fallback (in case PESTICIDE_AR_TO_EN is missing some)
        pesticide_names_common = [
            'bifenthrin', 'chlorpyrifos', 'imidacloprid', 'deltamethrin', 'cypermethrin',
            'abamectin', 'acetamiprid', 'thiamethoxam', 'carbendazim', 'buprofezin',
            'profenofos', 'metalaxyl', 'fipronil', 'emamectin', 'pyriproxyfen',
            'azoxystrobin', 'difenoconazole', 'lambda-cyhalothrin', 'spinosad'
        ]
        for en_name in pesticide_names_common:
            if en_name in query_lower:
                return en_name

        return None

    def _extract_context(self, query: str) -> dict:
        """
        Normalize the query and detect all entities (samples, neighborhoods, pesticide, period).

        Strips category sentinels (__cat__<key>) from detected_samples so that
        standard handlers always receive concrete sample names. The sentinel is
        preserved separately as 'category_key' for handlers that need it (e.g.
        Pattern 1B / violations-threshold).

        Returns a context dict consumed by process() routing tiers.
        """
        query_normalized = self._normalize_query(query)
        query_lower = query_normalized.lower()

        detected_samples_raw = self._detect_sample_types(query)
        detected_neighborhoods = self._detect_neighborhoods(query)
        detected_pesticide = self._detect_pesticide(query)
        detected_period = self._detect_time_period(query)
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
        }
