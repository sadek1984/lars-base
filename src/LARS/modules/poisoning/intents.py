"""
LARS :: poisoning-register intent pack
======================================
Tier-1 (deterministic template) entries for the existing 4-tier router.
Each intent carries Arabic + English trigger patterns, a parameterised SQL
template, and the answer/chart shape so the UI can render without a second
LLM round-trip.

Wire-up:
    from poisoning_intents import POISONING_INTENTS
    ROUTER.register_pack("poisoning", POISONING_INTENTS)

Anything that does not match here falls through to the normal
NL->SQL tier, which now has poisoning_incidents in its schema card.
"""

POISONING_INTENTS = [
    {
        "id": "psn.headline",
        "patterns_ar": [r"ملخص.*التسمم", r"وضع.*التسمم", r"كام حال[ةه].*تسمم",
                        r"احصائي[ةه].*التسمم"],
        "patterns_en": [r"poisoning (summary|overview|kpi)", r"how many .*poisoning"],
        "sql": "SELECT * FROM v_poisoning_kpi_headline",
        "render": "kpi_cards",
        "answer_ar": ("خلال {period}: {incidents} حالة تسمم غذائي، {people_affected} مصاب، "
                      "في {municipalities} بلديات. عدد قرارات الإدانة: {convictions}."),
        "answer_en": ("{incidents} food-poisoning incidents, {people_affected} people affected "
                      "across {municipalities} municipalities. Convictions: {convictions}."),
    },
    {
        "id": "psn.by_municipality",
        "patterns_ar": [r"(حسب|لكل|في) البلدي[ةه]", r"اي بلدي[ةه].*اكثر", r"توزيع.*البلديات"],
        "patterns_en": [r"by municipality", r"which municipality", r"worst municipality"],
        "sql": "SELECT * FROM v_poisoning_by_municipality LIMIT {limit}",
        "params": {"limit": 10},
        "render": "bar_chart",
        "chart": {"x": "municipality", "y": "people_affected",
                  "series": "incidents", "sort": "desc"},
    },
    {
        "id": "psn.trend",
        "patterns_ar": [r"اتجاه|منحن[يى]|شهري|بمرور الوقت|تطور"],
        "patterns_en": [r"trend|monthly|over time|by month"],
        "sql": "SELECT month_label, incidents, people_affected, convictions "
               "FROM v_poisoning_monthly",
        "render": "line_chart",
        "chart": {"x": "month_label", "y": ["incidents", "people_affected"]},
    },
    {
        "id": "psn.repeat_offenders",
        "patterns_ar": [r"متكرر|اكثر من مر[ةه]|قائم[ةه] المراقب[ةه]|منشات مكرر"],
        "patterns_en": [r"repeat|more than once|watchlist|recurring"],
        "sql": "SELECT * FROM v_poisoning_repeat_offenders LIMIT {limit}",
        "params": {"limit": 20},
        "render": "table",
        "empty_ar": "لا توجد منشأة تكرر بها الحادث خلال الفترة المحددة.",
        "empty_en": "No establishment recorded more than one incident in this period.",
    },
    {
        "id": "psn.agent_profile",
        "patterns_ar": [r"فتر[ةه] الحضان[ةه]", r"نوع.*الممرض|المسبب|العامل الممرض"],
        "patterns_en": [r"incubation", r"(likely )?(pathogen|agent|causative)"],
        "sql": "SELECT * FROM v_poisoning_agent_profile",
        "render": "table",
        "disclaimer_ar": "تصنيف استرشادي مبني على فترة الحضانة فقط — لا يغني عن التحليل المخبري.",
        "disclaimer_en": "Advisory classification from incubation window only — "
                         "not a substitute for laboratory confirmation.",
    },
    {
        "id": "psn.decision_audit",
        "patterns_ar": [r"قرار(ات)? اللجن[ةه]", r"الادان[ةه]", r"مراجع[ةه].*القرار"],
        "patterns_en": [r"committee decision", r"conviction", r"decision audit"],
        "sql": "SELECT * FROM v_poisoning_decision_audit",
        "render": "table",
        "disclaimer_ar": "المقارنة استرشادية وفق معايير دليل الوزارة المهيأة في النظام.",
        "disclaimer_en": "Comparison is advisory, based on the ministry-guide "
                         "thresholds configured in the system.",
    },
    {
        "id": "psn.establishment_lookup",
        "patterns_ar": [r"(محل|مطعم|منشا[ةه]).*(سجل|تاريخ|حالات)"],
        "patterns_en": [r"(history|record) (of|for) .*(restaurant|establishment)"],
        "sql": """
            SELECT incident_date, municipality, cases_count, incubation_hours,
                   decision_ar, decision_en, attribution_flag
            FROM poisoning_incidents
            WHERE establishment_key ILIKE '%' || {name} || '%'
               OR license_no = {name}
            ORDER BY incident_date DESC
        """,
        "params": {"name": None},          # filled by the entity extractor
        "render": "table",
        "pii": True,                        # gated by role — see notes
    },
    {
        "id": "psn.data_quality",
        "patterns_ar": [r"جود[ةه] البيانات|نواقص|بيانات ناقص[ةه]"],
        "patterns_en": [r"data quality|missing (data|fields)|completeness"],
        "sql": "SELECT * FROM v_poisoning_data_quality WHERE n > 0",
        "render": "table",
    },
]

# Schema card appended to the NL->SQL tier prompt so free-text questions
# still resolve correctly.
POISONING_SCHEMA_CARD = """
TABLE poisoning_incidents  -- سجل حالات التسمم الغذائي (municipal register)
  incident_id       TEXT    PSN-YYYY-NNNN
  incident_date     DATE    تاريخ البلاغ
  establishment_name TEXT   اسم المحل (as written)
  establishment_key TEXT    normalised Arabic name -- ALWAYS filter on this
  license_no        TEXT    رقم الرخصة (join key to inspections/lab samples)
  municipality      TEXT    اسم البلدية
  municipality_key  TEXT    normalised -- ALWAYS group on this
  incubation_hours  DOUBLE  فترة الحضانة (decimal hours, parsed)
  cases_count       INT     عدد المصابين
  kinship_code      TEXT    SINGLE_FAMILY | MULTIPLE_FAMILIES | UNKNOWN
  decision_code     TEXT    CONVICTED | NOT_CONVICTED | UNDER_REVIEW | UNKNOWN
  agent_class_code  TEXT    advisory pathogen class from incubation window
  attribution_flag  TEXT    LIKELY_ATTRIBUTABLE | UNLIKELY_ATTRIBUTABLE (advisory)
Rules: use the *_key columns for WHERE/GROUP BY; never SUM(license_no);
       counts below 5 are individually identifying — aggregate or gate.

IMPORTANT: queries mentioning تسمم / poisoning / الحضانة / المصابين refer ONLY to
    poisoning_incidents. Never answer them from chemistry_tidy — that table holds
    pesticide-residue samples and has no relationship to poisoning incidents.
"""