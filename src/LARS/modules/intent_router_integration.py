"""
=================================================================
INTEGRATION GUIDE: IntentRouter → core_query_engine.py
=================================================================

This shows EXACTLY how to wire the IntentRouter into the existing
process() method. The key insight is:

    OLD: 15+ compound IF conditions that miss query variations
    NEW: Router classifies ONCE, then a simple dispatch table routes

The handler methods (e.g. _handle_comprehensive_neighborhood) stay
EXACTLY the same — we only change HOW we decide to call them.
=================================================================
"""

# ==============================================================
# STEP 1: Add import at top of core_query_engine.py
# ==============================================================

# ADD after existing imports:
"""
from modules.intent_router import IntentRouter, Intent, QueryEntities
"""


# ==============================================================
# STEP 2: Initialize router in __init__
# ==============================================================

# ADD inside __init__, after self._load_mappings():
"""
        # Intent-based query router (replaces compound IF conditions)
        self.router = IntentRouter(dialect_synonyms=self.dialect_synonyms)
"""


# ==============================================================
# STEP 3: Add the dispatch table and new process method
# ==============================================================

# ADD this method to CoreQueryEngine class:
"""
    def _dispatch(self, intent: Intent, e: QueryEntities) -> Optional[Tuple[str, Optional[pd.DataFrame]]]:
        \"\"\"Route an intent + entities to the correct handler.

        Returns None if the intent is UNKNOWN (falls through to LLM).
        Handlers are the EXISTING methods — no changes needed to them.
        \"\"\"
        query = e.normalized_query

        # ── Neighborhood + Category analysis ──
        if intent == Intent.COMPREHENSIVE_NEIGHBORHOOD:
            return self._handle_comprehensive_neighborhood(
                query, e.samples, e.neighborhoods
            )

        if intent == Intent.LIST_TYPES_IN_NEIGHBORHOOD:
            # ★ THIS IS THE FIX: same handler, but called even without
            #   limit keywords. The handler already shows types + counts
            #   + limits — if the user didn't ask for limits, we still
            #   return the table (extra info doesn't hurt).
            return self._handle_comprehensive_neighborhood(
                query, e.samples, e.neighborhoods
            )

        if intent == Intent.NEIGHBORHOOD_PESTICIDES:
            return self._handle_neighborhood_pesticides(
                e.neighborhoods, e.wants_separately
            )

        if intent == Intent.NEIGHBORHOOD_RANKING:
            return self._handle_neighborhood_ranking()

        # ── N pesticides ──
        if intent == Intent.COUNT_N_PESTICIDES:
            if e.n_pesticides and len(e.n_pesticides) > 1 and e.wants_separately:
                return self._handle_multiple_n_pesticides(e.n_pesticides, e.samples)
            elif e.n_pesticides:
                return self._handle_n_pesticides(e.n_pesticides[-1], e.samples)

        # ── Pesticide queries ──
        if intent == Intent.FIND_PESTICIDE_IN_SAMPLE:
            if e.wants_limit_breakdown and e.pesticide:
                return self._handle_sample_pesticide_limit(
                    e.samples, e.pesticide, e.is_above_limit or True
                )
            if e.pesticide:
                return self._handle_find_pesticide_in_sample(e.pesticide, e.samples)

        if intent == Intent.FIND_PESTICIDE_ALL:
            if e.pesticide:
                return self._handle_find_pesticide_all(e.pesticide)

        if intent == Intent.LIST_PESTICIDES_IN_SAMPLE:
            return self._handle_list_pesticides(e.samples)

        if intent == Intent.PESTICIDE_STATISTICS:
            if e.pesticide:
                return self._handle_pesticide_stats(e.pesticide, e.samples, e.stat_types)

        # ── Sample counting ──
        if intent == Intent.COUNT_SAMPLES_LIMIT:
            return self._handle_count_samples_limit(
                e.samples, e.neighborhoods, e.is_above_limit
            )

        if intent == Intent.COUNT_SAMPLES_SIMPLE:
            return self._handle_simple_sample_count(e.samples, e.neighborhoods)

        if intent == Intent.UNIQUE_COUNT:
            return self._handle_unique_samples_count(e.samples, e.neighborhoods)

        # ── Other ──
        if intent == Intent.COMPREHENSIVE_ANALYSIS:
            return self._handle_comprehensive_analysis(e.samples)

        if intent == Intent.FACILITY_SEARCH:
            return self._handle_facility_search(query)

        if intent == Intent.RECIPIENT_SEARCH:
            # Extract name and delegate
            return self._handle_facility_search(query)  # or recipient-specific

        return None  # UNKNOWN → falls through to LLM
"""


# ==============================================================
# STEP 4: Replace the process() method
# ==============================================================

# The NEW process() is MUCH simpler:
"""
    def process(self, query: str) -> Tuple[str, Optional[pd.DataFrame]]:
        \"\"\"Process a query and return (response_text, DataFrame).

        Flow:
            1. Semantic recognizer (if available, high confidence)
            2. Intent router (covers 95% of queries)
            3. LLM fallback (complex/unknown queries)
            4. Unknown query help message
        \"\"\"
        # ── Step 1: Semantic Pattern Recognition (optional) ──
        if self.semantic_recognizer:
            semantic_result = self.semantic_recognizer.recognize(query)
            if semantic_result and semantic_result['confidence'] >= 0.75:
                result = self._route_by_semantic_pattern(
                    semantic_result['pattern_type'],
                    query, query.lower(), query.lower(),
                    self._detect_sample_types(query),
                    self._detect_neighborhoods(query),
                    self._detect_pesticide(query),
                )
                if result is not None:
                    return result

        # ── Step 2: Intent Router (main path) ──
        intent, entities = self.router.analyze(query)
        logging.info(f"🎯 Intent: {intent.name} | samples={entities.samples} "
                     f"neighborhoods={entities.neighborhoods} category={entities.category}")

        if intent != Intent.UNKNOWN:
            result = self._dispatch(intent, entities)
            if result is not None:
                return result

        # ── Step 3: LLM Fallback ──
        if self.llm_client is not None:
            llm_result = self._handle_llm_query(
                query,
                entities.samples,
                entities.neighborhoods,
                entities.pesticide,
            )
            if llm_result[0]:
                return llm_result

        # ── Step 4: Unknown ──
        return self._handle_unknown_query(query), None
"""


# ==============================================================
# WHAT THIS FIXES (examples)
# ==============================================================
#
# BEFORE (fails):
#   "ما هي انواع التوابل في حي الاسكان"
#   → Pattern 0 requires limit_keywords OR "عددها" → MISS
#   → Falls through all 14 patterns → "لم أتمكن من فهم سؤالك"
#
# AFTER (works):
#   Router: category="توابل", neighborhoods=["الإسكان"], wants_types=True
#   Intent: LIST_TYPES_IN_NEIGHBORHOOD
#   Dispatch: _handle_comprehensive_neighborhood() → shows types + counts
#
# MORE EXAMPLES THAT NOW WORK:
#
#   "التوابل في الاسكان"
#   → category="توابل", neighborhoods=["الإسكان"]
#   → LIST_TYPES_IN_NEIGHBORHOOD ✅
#
#   "ابغى انواع التوابل في الاسكان وكم عددها"
#   → (after dialect: "أريد انواع التوابل في الاسكان وكم عددها")
#   → category="توابل", neighborhoods=["الإسكان"], wants_types=True, wants_count=True
#   → COMPREHENSIVE_NEIGHBORHOOD ✅
#
#   "وش التوابل اللي في الاسكان"
#   → (after dialect: "ما التوابل اللي في الإسكان")
#   → category="توابل", neighborhoods=["الإسكان"]
#   → LIST_TYPES_IN_NEIGHBORHOOD ✅
#
#   "كم عينة توابل في حي الريان فوق الحد"
#   → category="توابل", neighborhoods=["الريان"], wants_count=True,
#     is_above_limit=True
#   → COMPREHENSIVE_NEIGHBORHOOD (with limit breakdown) ✅