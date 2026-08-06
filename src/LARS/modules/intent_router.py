"""
LARS Intent-Based Query Router.

Replaces rigid compound keyword conditions with a flexible
intent + entity system that gracefully handles query variations.

Problem solved:
    "انواع التوابل في حي الاسكان وما عددها وفوق/تحت الحد" → ✅ works
    "انواع التوابل في حي الاسكان"                          → ❌ fails
    Both should route to the same handler with different detail levels.

Architecture:
    1. Extract entities (samples, neighborhoods, pesticides, etc.)
    2. Detect intent from keywords + entity combination
    3. Route to handler, passing entities as context
    4. Handler adapts its output based on AVAILABLE entities
       (shows what it can, doesn't fail if optional info is missing)

Usage:
    from modules.intent_router import IntentRouter

    router = IntentRouter()
    intent, entities = router.analyze("انواع التوابل في حي الاسكان")
    # intent = Intent.LIST_TYPES_IN_NEIGHBORHOOD
    # entities = {category: "توابل", neighborhoods: ["الإسكان"]}
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple

from modules.mappings import (
    PESTICIDE_AR_TO_EN,
    PESTICIDE_AR_TO_EN_NORM,
    SAMPLE_CORRECTIONS,
    SAMPLE_EN_TO_AR,
    NEIGHBORHOOD_CORRECTIONS,
    NEIGHBORHOOD_CORRECTIONS_NORM,
    normalize_arabic_query,
    normalize_arabic_text,
    PESTICIDE_AR_TO_EN_NORM_NOSPACE,
)

logger = logging.getLogger(__name__)


# ============================================================================
# INTENT DEFINITIONS
# ============================================================================

class Intent(Enum):
    """All recognized query intents, ordered by specificity."""

    # ── Neighborhood + Category analysis ──
    COMPREHENSIVE_NEIGHBORHOOD = auto()  # types + count + limits in neighborhood
    LIST_TYPES_IN_NEIGHBORHOOD = auto()  # just list types in neighborhood
    NEIGHBORHOOD_PESTICIDES = auto()     # pesticides found in neighborhood
    NEIGHBORHOOD_RANKING = auto()        # rank neighborhoods by violations

    # ── Sample counting ──
    COUNT_SAMPLES_LIMIT = auto()         # count above/below limit
    COUNT_SAMPLES_COMPLIANCE = auto()    # count compliant/non-compliant
    COUNT_SAMPLES_SIMPLE = auto()        # just count (no conditions)
    COUNT_N_PESTICIDES = auto()          # samples with N pesticides

    # ── Pesticide queries ──
    FIND_PESTICIDE_IN_SAMPLE = auto()    # pesticide X in sample Y
    FIND_PESTICIDE_ALL = auto()          # search for pesticide everywhere
    LIST_PESTICIDES_IN_SAMPLE = auto()   # all pesticides in sample type
    PESTICIDE_STATISTICS = auto()        # stats for a pesticide

    # ── Other ──
    COMPREHENSIVE_ANALYSIS = auto()      # full analysis for sample type
    FACILITY_SEARCH = auto()             # search by establishment
    RECIPIENT_SEARCH = auto()            # search by recipient
    UNIQUE_COUNT = auto()                # unique sample count

    UNKNOWN = auto()

    #  (a) Intent enum
    POISONING_HEADLINE       = auto()
    POISONING_BY_MUNICIPALITY = auto()
    POISONING_TREND          = auto()
    POISONING_REPEAT         = auto()
    POISONING_AGENT          = auto()
    POISONING_AUDIT          = auto()
    POISONING_ESTABLISHMENT  = auto()
    POISONING_QUALITY        = auto()

# ============================================================================
# ENTITY CONTAINER
# ============================================================================

@dataclass
class QueryEntities:
    """All entities extracted from a user query.

    Handlers receive this object and adapt their behavior based on
    which fields are populated vs. None/empty.
    """

    samples: List[str] = field(default_factory=list)
    neighborhoods: List[str] = field(default_factory=list)
    pesticide: Optional[str] = None
    category: Optional[str] = None  # "توابل", "خضار", "فواكه", "ورقيات", "مكسرات"

    # ── Modifiers (optional enrichments) ──
    is_above_limit: Optional[bool] = None   # True=above, False=below, None=both/unspecified
    wants_limit_breakdown: bool = False      # user explicitly asked about limits
    wants_count: bool = False                # user asked "how many" / "عدد"
    wants_types: bool = False                # user asked "what types" / "انواع"
    wants_separately: bool = False           # "كل على حده"
    wants_unique: bool = False               # "فريدة" / "unique"
    n_pesticides: Optional[List[int]] = None # specific pesticide counts

    # ── Statistics modifiers ──
    stat_types: List[str] = field(default_factory=list)  # ["max", "min", "avg", ...]

    # ── Raw ──
    raw_query: str = ""
    normalized_query: str = ""


# ============================================================================
# CATEGORY DETECTION
# ============================================================================

# Maps keyword → (category_name, SQL filter)
CATEGORY_MAP: Dict[str, Tuple[str, str]] = {
    "توابل": ("التوابل", """("نوع العينة" LIKE '%توابل%' OR "اسم العينة" IN ('كمون','هيل','زعتر','كركم','بهارات','فلفل اسود','قرفة','يانسون','كزبرة','شمر','قرنفل','محلب'))"""),
    "التوابل": ("التوابل", """("نوع العينة" LIKE '%توابل%' OR "اسم العينة" IN ('كمون','هيل','زعتر','كركم','بهارات','فلفل اسود','قرفة','يانسون','كزبرة','شمر','قرنفل','محلب'))"""),
    "بهارات": ("التوابل", """("نوع العينة" LIKE '%توابل%' OR "اسم العينة" IN ('كمون','هيل','زعتر','كركم','بهارات','فلفل اسود','قرفة','يانسون','كزبرة','شمر','قرنفل','محلب'))"""),
    "خضار": ("الخضار", """("نوع العينة" LIKE '%خضر%' OR "اسم العينة" IN ('طماطم','خيار','كوسة','باذنجان','فلفل','بامية','فاصوليا','زهرة','بروكلي','ملفوف'))"""),
    "الخضار": ("الخضار", """("نوع العينة" LIKE '%خضر%' OR "اسم العينة" IN ('طماطم','خيار','كوسة','باذنجان','فلفل','بامية','فاصوليا','زهرة','بروكلي','ملفوف'))"""),
    "خضروات": ("الخضار", """("نوع العينة" LIKE '%خضر%' OR "اسم العينة" IN ('طماطم','خيار','كوسة','باذنجان','فلفل','بامية','فاصوليا','زهرة','بروكلي','ملفوف'))"""),
    "فاكهة": ("الفواكه", """("نوع العينة" LIKE '%فاكه%' OR "نوع العينة" LIKE '%فواكه%' OR "اسم العينة" IN ('تفاح','برتقال','عنب','مانجو','توت','رمان','ليمون','فراولة','كمثرى'))"""),
    "فواكه": ("الفواكه", """("نوع العينة" LIKE '%فاكه%' OR "نوع العينة" LIKE '%فواكه%' OR "اسم العينة" IN ('تفاح','برتقال','عنب','مانجو','توت','رمان','ليمون','فراولة','كمثرى'))"""),
    "ورقيات": ("الورقيات", """("نوع العينة" LIKE '%ورقي%' OR "اسم العينة" IN ('خس','جرجير','بقدونس','كزبرة','شبت','نعناع','سبانخ','ملوخية','رجلة','سلق'))"""),
    "الورقيات": ("الورقيات", """("نوع العينة" LIKE '%ورقي%' OR "اسم العينة" IN ('خس','جرجير','بقدونس','كزبرة','شبت','نعناع','سبانخ','ملوخية','رجلة','سلق'))"""),
    "مكسرات": ("المكسرات", """("نوع العينة" LIKE '%مكسر%' OR "اسم العينة" IN ('لوز','فستق','كاجو','بندق','فول سوداني','سمسم','بيكان'))"""),
    "المكسرات": ("المكسرات", """("نوع العينة" LIKE '%مكسر%' OR "اسم العينة" IN ('لوز','فستق','كاجو','بندق','فول سوداني','سمسم','بيكان'))"""),
    "حبوب": ("الحبوب", """("نوع العينة" LIKE '%حبوب%' OR "اسم العينة" IN ('قمح','رز','ذرة','عدس','شوفان','دقيق'))"""),
    "الحبوب": ("الحبوب", """("نوع العينة" LIKE '%حبوب%' OR "اسم العينة" IN ('قمح','رز','ذرة','عدس','شوفان','دقيق'))"""),
}


# ============================================================================
# INTENT ROUTER
# ============================================================================

class IntentRouter:
    """Analyze a query and return (Intent, QueryEntities).

    The router extracts entities FIRST, then determines intent from the
    combination of entities + keywords. This means the same handler can
    serve multiple query phrasings — it just adjusts its output.

    Args:
        dialect_synonyms: Optional dict of dialect normalization rules.
    """

    def __init__(self, dialect_synonyms: Optional[Dict[str, str]] = None) -> None:
        self.dialect_synonyms = dialect_synonyms or {}

        # ── Keyword groups ──
        self._above_keywords = frozenset([
            "فوق الحد", "تجاوز", "مخالف", "راسب", "راسبة", "غير مطابق",
            "مخالفة", "المخالفات", "متجاوز", "متجاوزة", "الغير مطابقة",
            "above limit", "exceeding", "non-compliant", "violation",
        ])
        self._below_keywords = frozenset([
            "تحت الحد", "ضمن الحد", "مطابق", "مطابقة", "ناجح", "سليم",
            "below limit", "within limit", "compliant", "passing", "safe",
        ])
        self._count_keywords = frozenset([
            "عدد", "كم", "كام", "count", "how many", "عددها", "ماعددها",
        ])
        self._type_keywords = frozenset([
            "انواع", "أنواع", "types", "الموجودة", "موجوده", "ماهي",
            "ما هي", "what are", "what types",
        ])
        self._pesticide_list_keywords = frozenset([
            "المبيدات", "مبيدات", "pesticides",
        ])
        self._stats_keywords = {
            "max": ["اعلي", "أعلى", "اعلى", "أكبر", "max", "maximum", "highest"],
            "min": ["اقل", "أقل", "ادنى", "أدنى", "min", "minimum", "lowest"],
            "avg": ["متوسط", "المتوسط", "average", "mean"],
            "median": ["الوسيط", "وسيط", "median"],
            "range": ["المدى", "المدي", "range"],
            "std": ["الانحراف", "deviation", "std"],
        }
        self._ranking_keywords = frozenset([
            "ترتيب", "ranking", "الاكثر", "الأكثر", "rank",
        ])
        self._search_keywords = frozenset([
            "ابحث", "دور", "اوجد", "find", "search", "locate",
        ])
        self._separately_keywords = frozenset([
            "كل علي حده", "كل على حده", "كل على حدة",
            "بشكل منفصل", "each separately", "separately",
        ])
        self._unique_keywords = frozenset([
            "فريدة", "فريد", "unique", "distinct", "كود العينة",
        ])
        self._comprehensive_keywords = frozenset([
            "تحليل شامل", "تقرير شامل", "احصائيات", "ملخص شامل",
        ])
        self._facility_keywords = frozenset([
            "منشأة", "المنشأة", "منشاة", "مصنع", "مطعم", "محل",
        ])
        self._recipient_keywords = frozenset([
            "المستلم", "مستلم", "recipient",
        ])

    # ────────────────────────────────────────────────────────────
    # PUBLIC API
    # ────────────────────────────────────────────────────────────

    def analyze(self, query: str) -> Tuple[Intent, QueryEntities]:
        """Extract entities and determine intent.

        Args:
            query: Raw user query (Arabic or English).

        Returns:
            (Intent, QueryEntities) tuple. The handler should check
            the entities to decide what level of detail to show.
        """
        # ── Normalize ──
        normalized = self._normalize(query)

        # ── Extract all entities ──
        entities = QueryEntities(
            raw_query=query,
            normalized_query=normalized,
        )

        entities.samples = self._extract_samples(normalized)
        entities.neighborhoods = self._extract_neighborhoods(normalized)
        entities.pesticide = self._extract_pesticide(normalized)
        entities.category = self._extract_category(normalized)

        # ── Extract modifiers ──
        entities.wants_types = self._has_any(normalized, self._type_keywords)
        entities.wants_count = self._has_any(normalized, self._count_keywords)
        entities.wants_separately = self._has_any(normalized, self._separately_keywords)
        entities.wants_unique = self._has_any(normalized, self._unique_keywords)
        entities.wants_limit_breakdown = (
            self._has_any(normalized, self._above_keywords)
            or self._has_any(normalized, self._below_keywords)
        )

        if self._has_any(normalized, self._above_keywords) and not self._has_any(normalized, self._below_keywords):
            entities.is_above_limit = True
        elif self._has_any(normalized, self._below_keywords) and not self._has_any(normalized, self._above_keywords):
            entities.is_above_limit = False
        # else: None → show both or not applicable

        entities.stat_types = self._extract_stat_types(normalized)
        entities.n_pesticides = self._extract_n_pesticides(normalized)

        # ── Determine intent ──
        intent = self._classify_intent(entities, normalized)

        logger.debug("Intent: %s | Entities: samples=%s, neighborhoods=%s, category=%s, pesticide=%s",
                     intent.name, entities.samples, entities.neighborhoods, entities.category, entities.pesticide)

        return intent, entities

    # ────────────────────────────────────────────────────────────
    # ENTITY EXTRACTION
    # ────────────────────────────────────────────────────────────

    def _extract_samples(self, query: str) -> List[str]:
        """Detect Arabic/English sample names."""
        detected = []
        for ar_name, canonical in SAMPLE_CORRECTIONS.items():
            if ar_name in query and canonical not in detected:
                detected.append(canonical)
        if not detected:
            q_lower = query.lower()
            for en_name, ar_canonical in SAMPLE_EN_TO_AR.items():
                if en_name in q_lower and ar_canonical not in detected:
                    detected.append(ar_canonical)
        return detected

    def _extract_neighborhoods(self, query: str) -> List[str]:
        """Detect neighborhood names, normalized match."""
        detected = []
        norm_query = normalize_arabic_text(query)
        for norm_variant, canonical in NEIGHBORHOOD_CORRECTIONS_NORM.items():
            if norm_variant in norm_query and canonical not in detected:
                detected.append(canonical)
        return detected

    def _extract_pesticide(self, query: str) -> Optional[str]:
        """Detect a single pesticide (Arabic → English), normalized + space-insensitive match."""
        norm_query = normalize_arabic_text(query)
        for norm_key in sorted(PESTICIDE_AR_TO_EN_NORM.keys(), key=len, reverse=True):
            if norm_key in norm_query:
                return PESTICIDE_AR_TO_EN_NORM[norm_key]

        nospace_query = norm_query.replace(" ", "")
        for norm_key in sorted(PESTICIDE_AR_TO_EN_NORM_NOSPACE.keys(), key=len, reverse=True):
            if norm_key in nospace_query:
                return PESTICIDE_AR_TO_EN_NORM_NOSPACE[norm_key]

        return None

    def _extract_category(self, query: str) -> Optional[str]:
        """Detect a food category (توابل, خضار, فواكه, etc.)."""
        for keyword in CATEGORY_MAP:
            if keyword in query:
                return keyword
        return None

    def _extract_stat_types(self, query: str) -> List[str]:
        """Detect requested statistics types."""
        found = []
        q_lower = query.lower()
        for stat_type, keywords in self._stats_keywords.items():
            if any(kw in q_lower or kw in query for kw in keywords):
                found.append(stat_type)
        return found

    def _extract_n_pesticides(self, query: str) -> Optional[List[int]]:
        """Extract pesticide count numbers if query is about N pesticides."""
        pesticide_kw = ["مبيد", "مبيدات", "pesticide", "pesticides"]
        if not any(kw in query for kw in pesticide_kw):
            return None
        numbers = re.findall(r"(\d+)", query)
        if numbers:
            return [int(n) for n in numbers if 1 <= int(n) <= 50]
        return None

    # ────────────────────────────────────────────────────────────
    # INTENT CLASSIFICATION
    # ────────────────────────────────────────────────────────────

    def _classify_intent(self, e: QueryEntities, query: str) -> Intent:

        from modules.poisoning import classify_poisoning, INTENT_ENUM_NAME
        psn = classify_poisoning(query)
        if psn:
            return Intent[INTENT_ENUM_NAME[psn]]
        """Determine intent from entities + keywords.

        Rules are ordered from MOST SPECIFIC to LEAST SPECIFIC.
        The first match wins.
        """
        q_lower = query.lower()
        has_neighborhoods = bool(e.neighborhoods)
        has_samples = bool(e.samples)
        has_category = bool(e.category)
        has_pesticide = bool(e.pesticide)

        # ── 1. Category/types in neighborhood ──
        # "انواع التوابل في حي الاسكان" (with or without limit info)
        if (has_category or e.wants_types) and has_neighborhoods:
            if e.wants_limit_breakdown or e.wants_count:
                return Intent.COMPREHENSIVE_NEIGHBORHOOD
            return Intent.LIST_TYPES_IN_NEIGHBORHOOD

        # ── 2. Pesticide-specific stats ──
        if has_pesticide and e.stat_types:
            return Intent.PESTICIDE_STATISTICS

        # ── 3. N pesticides ──
        if e.n_pesticides:
            return Intent.COUNT_N_PESTICIDES

        # ── 4. Pesticide + sample ──
        if has_pesticide and has_samples:
            if e.wants_limit_breakdown:
                return Intent.FIND_PESTICIDE_IN_SAMPLE  # will show limit info
            return Intent.FIND_PESTICIDE_IN_SAMPLE

        # ── 5. Pesticide + neighborhood ──
        if has_neighborhoods and self._has_any(query, self._pesticide_list_keywords):
            return Intent.NEIGHBORHOOD_PESTICIDES

        # ── 6. Neighborhood ranking ──
        if self._has_any(query, self._ranking_keywords) and ("حي" in query or "أحياء" in query or "احياء" in query):
            return Intent.NEIGHBORHOOD_RANKING

        # ── 7. Comprehensive analysis ──
        if self._has_any(query, self._comprehensive_keywords) and has_samples:
            return Intent.COMPREHENSIVE_ANALYSIS

        # ── 8. Facility / Recipient search ──
        if self._has_any(query, self._facility_keywords):
            return Intent.FACILITY_SEARCH
        if self._has_any(query, self._recipient_keywords):
            return Intent.RECIPIENT_SEARCH

        # ── 9. Pesticide in all samples ──
        if has_pesticide and not has_samples:
            if self._has_any(query, self._search_keywords):
                return Intent.FIND_PESTICIDE_ALL
            if e.wants_count:
                return Intent.FIND_PESTICIDE_ALL
            return Intent.FIND_PESTICIDE_ALL

        # ── 10. Sample counting with conditions ──
        if has_samples and (e.wants_limit_breakdown or e.is_above_limit is not None):
            return Intent.COUNT_SAMPLES_LIMIT

        # ── 11. Unique count ──
        if has_samples and e.wants_unique:
            return Intent.UNIQUE_COUNT

        # ── 12. List pesticides in sample ──
        if has_samples and self._has_any(query, self._pesticide_list_keywords):
            return Intent.LIST_PESTICIDES_IN_SAMPLE

        # ── 13. Simple sample count ──
        if has_samples and e.wants_count:
            return Intent.COUNT_SAMPLES_SIMPLE

        # ── 14. Category in neighborhood (without "types" keyword) ──
        # "التوابل في حي الاسكان" — no "انواع" but still category + neighborhood
        if has_category and has_neighborhoods:
            return Intent.LIST_TYPES_IN_NEIGHBORHOOD

        # ── 15. Samples in neighborhood (general) ──
        if has_samples and has_neighborhoods:
            if e.wants_count:
                return Intent.COUNT_SAMPLES_SIMPLE
            return Intent.COUNT_SAMPLES_SIMPLE

        return Intent.UNKNOWN

    # ────────────────────────────────────────────────────────────
    # HELPERS
    # ────────────────────────────────────────────────────────────

    def _normalize(self, query: str) -> str:
        """Apply dialect synonyms + Arabic numeral conversion."""
        for dialect, standard in self.dialect_synonyms.items():
            query = query.replace(dialect, standard)
        return normalize_arabic_query(query)

    @staticmethod
    def _has_any(text: str, keywords: frozenset) -> bool:
        """Check if text contains any keyword from the set."""
        return any(kw in text for kw in keywords)

    # ────────────────────────────────────────────────────────────
    # UTILITY: get SQL filter for category
    # ────────────────────────────────────────────────────────────

    @staticmethod
    def get_category_sql(category_keyword: Optional[str]) -> Tuple[str, str]:
        """Get (display_name, SQL_filter) for a food category.

        Args:
            category_keyword: Arabic category keyword or None.

        Returns:
            (name, sql_filter) tuple. If no category matched,
            returns ("العينات", "") — no filter applied.
        """
        if category_keyword and category_keyword in CATEGORY_MAP:
            return CATEGORY_MAP[category_keyword]
        return ("العينات", "")