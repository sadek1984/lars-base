"""
LARS :: poisoning router gate
=============================
Replaces the regex patterns in intents.py for classification purposes.

Rationale: the token "تسمم" appears nowhere in the pesticide-residue dataset,
so it is a reliable DOMAIN discriminator. Any query containing it belongs to
poisoning_incidents and must never be answered from chemistry_tidy.

Structure:
  1. is_poisoning_domain(q)  -> bool   (the gate)
  2. classify_poisoning(q)   -> intent id, defaulting to the headline summary
                                 rather than falling through to NL->SQL

Call classify_poisoning() at the TOP of _classify_intent, before any generic
count rules — "كم عدد" is exactly the phrase that pulled the query into the
sample-count path.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Optional

# ---------------------------------------------------------------------------
# 0. query normalisation (independent of the engine's own, so behaviour is
#    identical whether or not the caller pre-normalised)
# ---------------------------------------------------------------------------

_DIACRITICS = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")


def norm_q(q: str) -> str:
    s = unicodedata.normalize("NFKC", q or "")
    s = _DIACRITICS.sub("", s).replace("\u0640", "")
    s = (s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
          .replace("ى", "ي").replace("ة", "ه")
          .replace("ؤ", "و").replace("ئ", "ي"))
    s = re.sub(r"[؟?!.,،]", " ", s)
    return re.sub(r"\s+", " ", s).strip().lower()


# ---------------------------------------------------------------------------
# 1. domain gate
# ---------------------------------------------------------------------------

DOMAIN_MARKERS = (
    "تسمم", "التسمم", "مسمم",          # the decisive token
    "poisoning", "food poison",
    "فتره الحضانه", "الحضانه",          # incubation
    "قرار اللجنه", "الادانه", "ادانه",  # committee vocabulary
    "المصابين",
)


def is_poisoning_domain(query: str) -> bool:
    q = norm_q(query)
    return any(m in q for m in DOMAIN_MARKERS)


# ---------------------------------------------------------------------------
# 2. intent classification WITHIN the domain
#    Order matters: first match wins, so specific before generic.
# ---------------------------------------------------------------------------

INTENT_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("psn.data_quality", (
        "جوده البيانات", "جوده بيانات", "نواقص", "بيانات ناقصه", "اكتمال",
        "data quality", "missing", "completeness")),
    ("psn.repeat_offenders", (
        "متكرر", "تكرار", "اكثر من مره", "قائمه المراقبه", "مكرره",
        "repeat", "recurring", "watchlist", "more than once")),
    ("psn.decision_audit", (
        "قرار اللجنه", "قرارات اللجنه", "الادانه", "ادانه", "عدم ادانه",
        "مراجعه القرار", "توافق", "audit", "decision", "conviction")),
    ("psn.agent_profile", (
        "الحضانه", "فتره الحضانه", "المسبب", "الممرض", "العامل الممرض",
        "بكتيريا", "جرثومه", "incubation", "pathogen", "agent", "causative")),
    ("psn.by_municipality", (
        "بلديه", "البلديات", "بلديات", "توزيع", "منطقه", "اي بلديه",
        "municipality", "by municipality", "region")),
    ("psn.trend", (
        "اتجاه", "منحني", "شهري", "بمرور الوقت", "تطور", "شهور", "الاشهر",
        "trend", "monthly", "over time", "by month")),
    ("psn.establishment_lookup", (
        "مطعم", "محل", "منشاه", "سجل المنشاه", "رقم الرخصه", "الرخصه",
        "restaurant", "establishment", "license")),
    # deliberately last: the catch-all for the domain
    ("psn.headline", (
        "كم", "عدد", "ملخص", "احصائي", "نظره عامه", "وضع", "حالات", "حاله",
        "how many", "summary", "overview", "kpi", "statistics", "total")),
)


def classify_poisoning(query: str, strict: bool = False) -> Optional[str]:
    """
    Returns a poisoning intent id, or None if the query is not in-domain.

    strict=False (default): any in-domain query with no specific keyword match
    still resolves to psn.headline. This is the important behaviour — it stops
    a poisoning question from ever reaching NL->SQL and being answered from
    chemistry_tidy.
    """
    if not is_poisoning_domain(query):
        return None
    q = norm_q(query)
    for intent_id, keywords in INTENT_KEYWORDS:
        if any(k in q for k in keywords):
            return intent_id
    return None if strict else "psn.headline"


# ---------------------------------------------------------------------------
# 3. intent-id <-> enum name (explicit beats clever)
# ---------------------------------------------------------------------------

INTENT_ENUM_NAME = {
    "psn.headline":              "POISONING_HEADLINE",
    "psn.by_municipality":       "POISONING_BY_MUNICIPALITY",
    "psn.trend":                 "POISONING_TREND",
    "psn.repeat_offenders":      "POISONING_REPEAT",
    "psn.agent_profile":         "POISONING_AGENT",
    "psn.decision_audit":        "POISONING_AUDIT",
    "psn.establishment_lookup":  "POISONING_ESTABLISHMENT",
    "psn.data_quality":          "POISONING_QUALITY",
}
ENUM_NAME_INTENT = {v: k for k, v in INTENT_ENUM_NAME.items()}


if __name__ == "__main__":
    cases = [
        "كم عدد حالات التسمم؟",
        "كم عدد حالات التسمم الغذائي هذا العام",
        "ملخص التسمم",
        "أي بلدية فيها أكثر حالات تسمم؟",
        "توزيع حالات التسمم حسب البلديات",
        "اتجاه حالات التسمم الشهري",
        "اعرض قرارات اللجنة في حالات التسمم",
        "ما فترة الحضانة في حالات التسمم؟",
        "المنشآت المتكررة في التسمم",
        "جودة بيانات التسمم",
        "how many poisoning incidents",
        "poisoning by municipality",
        "كم عدد المصابين؟",
        # must NOT be captured:
        "كم عينة كوسة غير مطابقة؟",
        "كم عدد العينات المطابقة؟",
        "أعلى تركيز للكلوربيريفوس",
    ]
    for c in cases:
        r = classify_poisoning(c)
        print(f"  {'--' if r is None else r:28} | {c}")