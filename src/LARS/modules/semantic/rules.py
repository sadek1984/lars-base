"""
Deterministic QuerySpecs for common questions, tried BEFORE the LLM.

    rule_spec(question) -> QuerySpec | None

Ranking of groups by non-compliance:
    (أعلى|أخطر|أكثر|أسوأ) [N] (أحياء|بلديات|منتجات)
    + (غير مطابقة | عدم المطابقة | مخالفة | مخالفات | رسوب | راسبة)
    [+ نسبة] [+ period]
→ metric noncompliant_count (official verdict), ranked by count, each group
  with its total samples; noncompliance_rate (≥10-sample rule) only when the
  question says "نسبة". group_by, top_n and period come from the question.

The match must be clean: every word is part of the pattern, a period word
or a filler word. Anything else (a product, place, pesticide, year, quarter,
two months, …) → None, and the LLM fills the spec as before. The spec then
goes through the same validator / coverage check / answer path.
"""
from __future__ import annotations

from typing import Optional

from modules.query.text_norm import (_strip_clitics, compliance_intent, named_years, names_quarter, norm,
                                     number_value, parse_period, tokens)
from modules.semantic.query_spec import QuerySpec

_RANK = {"اعلي", "اخطر", "اكثر", "اسوا"}
_GROUPS = {"احياء": "neighborhood", "بلديات": "municipality", "منتجات": "product"}
_VIOLATION = {"مخالفه", "مخالفات", "رسوب", "راسبه", "راسبات", "غير", "مطابقه"}
_MONTHS = {"يناير": 1, "فبراير": 2, "مارس": 3, "ابريل": 4, "مايو": 5, "يونيو": 6, "يوليو": 7,
           "اغسطس": 8, "سبتمبر": 9, "اكتوبر": 10, "نوفمبر": 11, "ديسمبر": 12}
_PERIOD_WORDS = {"اخر", "خلال", "اخير", "اخيره", "ماضي", "ماضيه", "ماضيين", "فائت", "سابق",
                 "يوم", "يومين", "ايام", "اسبوع", "اسبوعين", "اسابيع", "شهر", "شهرين", "اشهر", "شهور",
                 "هذا", "حالي"}
_FILLER = {"ما", "هي", "هو", "ماهي", "وش", "ايش", "شو", "في", "من", "حيث", "حسب", "بحسب", "علي",
           "عدد", "عينات", "عينه", "اعطني", "عطني", "ابي", "ابغي", "لي", "هات", "اذكر", "التي", "اللي",
           "فيها", "بها", "لديها", "كانت", "و", "نسبه"}


def rule_spec(question: str) -> Optional[QuerySpec]:
    toks = tokens(question)                       # norm(): "عدم المطابقة" → "غير المطابقه"
    bare = [_strip_clitics(t) for t in toks]
    if not toks or named_years(question) or names_quarter(question):
        return None

    # (rank) [N] (group)
    group = top_n = None
    for i, b in enumerate(bare):
        if b not in _RANK:
            continue
        j = i + 1
        n = number_value(toks[j]) if j < len(toks) else None
        if n is not None:
            j += 1
        if j < len(bare) and bare[j] in _GROUPS:
            group, top_n = _GROUPS[bare[j]], n
            break
    if group is None:
        return None

    q = norm(question)
    violation = compliance_intent(question) == "non_compliant" or any(
        b.startswith("مخالف") or b in ("رسوب", "راسبه", "راسبات") for b in bare)
    if not violation:
        return None

    # period: relative, one named month, or "this month"; nothing else
    months = {_MONTHS[b] for b in bare if b in _MONTHS}
    parsed = parse_period(question)
    if len(months) > 1 or (months and parsed):
        return None
    if parsed:
        period = {"type": "relative", "n": parsed[0], "unit": parsed[1]}
    elif months:
        period = {"type": "absolute_month", "month": months.pop()}
    elif "هذا الشهر" in q or "الشهر الحالي" in q:
        period = {"type": "latest_month"}
    else:
        period = None

    # clean: every word belongs to the pattern
    allowed = _RANK | set(_GROUPS) | _VIOLATION | _PERIOD_WORDS | _FILLER | set(_MONTHS)
    for t, b in zip(toks, bare):
        if b in allowed or t in allowed or number_value(t) is not None or b.startswith("مخالف"):
            continue
        return None

    spec = {"metric": "noncompliance_rate" if "نسبه" in bare else "noncompliant_count", "group_by": group}
    if top_n is not None:
        spec["top_n"] = max(1, min(int(top_n), 50))
    if period:
        spec["period"] = period
    try:
        return QuerySpec.model_validate(spec)
    except ValueError:
        return None
