"""
text_norm.py — the one Arabic text normalization every query layer shares.

Before this module, each layer matched raw strings its own way: the entity
resolver normalized (hamza, ة/ه, ى/ي), but the Tier-0 compliance check,
the intent router's keyword sets and the keyword-pattern tier compared raw
text. So "غير المطابقه" (ه) or "اداء" (no hamza) matched in one layer and
not in the next, and the question silently took a different path.

Provided here:
  norm(text)             — tashkeel/tatweel stripped, hamza forms unified,
                           ة→ه, ى→ي, Arabic-Indic digits → 0-9, lower-cased
  NormText               — a str that keeps the original text (for regexes,
                           display, SQL params) but whose `in` compares
                           normalized forms on both sides
  compliance_intent()    — official-verdict vocabulary, incl. dialect/verb forms
  count_for_nouns()      — a number only when it quantifies a count noun
  parse_period()         — relative periods ("آخر ٣ شهور", "الأشهر الثلاثة
                           الأخيرة", "الشهر الماضي") and has_period_phrase()
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Iterable, List, Optional, Tuple

from modules.query.mappings import normalize_arabic_text

_INDIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩٫", "0123456789.")
_TOKEN_PUNCT = "؟?،,.!:;()[]\"'«»…"


@lru_cache(maxsize=4096)
def norm(text: str) -> str:
    """Canonical form for matching: normalize_arabic_text (tashkeel, tatweel,
    hamza carriers, ى→ي, ة→ه), Western digits, lower case, single spaces."""
    if not text:
        return ""
    t = normalize_arabic_text(str(text)).translate(_INDIC_DIGITS).lower()
    return " ".join(t.split())


class NormText(str):
    """The original question text, with normalization-insensitive `in`.

    `"غير مطابقة" in NormText("العينات غير مطابقه")` is True. Everything
    else (slicing, regexes, formatting, SQL parameters) sees the original
    string, so wrapping a query changes keyword matching only.
    """

    def __new__(cls, value: str):
        obj = super().__new__(cls, value)
        obj.norm = norm(value)
        return obj

    def __contains__(self, needle) -> bool:  # type: ignore[override]
        return norm(needle) in self.norm


def contains_any(text: str, needles: Iterable[str]) -> bool:
    t = norm(text)
    return any(norm(n) in t for n in needles)


def _strip_clitics(word: str) -> str:
    """'والعينات' → 'عينات', 'للمنتجات' → 'منتجات' (one prefix, ال, …)."""
    w = word
    for p in ("وال", "بال", "فال", "كال", "لل", "ال"):
        if w.startswith(p) and len(w) - len(p) >= 2:
            return w[len(p):]
    if w[:1] in ("و", "ب", "ل", "ف") and len(w) > 3:
        rest = w[1:]
        if rest.startswith("ال") and len(rest) > 4:
            return rest[2:]
    return w


def tokens(text: str) -> List[str]:
    """Normalized words with punctuation trimmed (clitics kept)."""
    out = []
    for w in norm(text).split():
        w = w.strip(_TOKEN_PUNCT)
        if w:
            out.append(w)
    return out


# ── Compliance (official verdict, sample_result) ─────────────────────────────
# Forms are normalized (ة→ه, hamza removed). A negator directly before a
# "match" word flips it to non-compliant: "ما طابقت", "غير المطابقه", "لم تطابق".
_NEGATORS = {"غير", "الغير", "ما", "لم", "لا"}
_MATCH_STEMS = ("مطابق", "طابق", "تطابق")
_NON_COMPLIANT_STEMS = ("راسب", "رسب", "فاشل", "فشل", "مرفوض")   # not "رواسب" (= residues)
_COMPLIANT_STEMS = ("ناجح", "نجح", "مقبول")


def compliance_intent(text: str) -> Optional[str]:
    """'non_compliant' | 'compliant' | None for the official-verdict path.
    Non-compliant wins when both appear ("كم مطابقة وكم غير مطابقة")."""
    toks = [_strip_clitics(t) for t in tokens(text)]
    non = comp = False
    for i, t in enumerate(toks):
        prev = toks[i - 1] if i else ""
        if t.startswith(_MATCH_STEMS):
            if prev in _NEGATORS:
                non = True
            else:
                comp = True
        elif t.startswith(_NON_COMPLIANT_STEMS):
            non = True
        elif t.startswith(_COMPLIANT_STEMS) and prev not in _NEGATORS:
            comp = True
    if non:
        return "non_compliant"
    return "compliant" if comp else None


# ── Numbers that quantify a count noun ───────────────────────────────────────
_NUMBER_WORDS = {
    "واحد": 1, "واحده": 1, "اثنين": 2, "اثنان": 2, "اثنتين": 2, "اثنتان": 2,
    "ثلاث": 3, "ثلاثه": 3, "اربع": 4, "اربعه": 4, "خمس": 5, "خمسه": 5,
    "ست": 6, "سته": 6, "سبع": 7, "سبعه": 7, "ثمان": 8, "ثماني": 8, "ثمانيه": 8,
    "تسع": 9, "تسعه": 9, "عشر": 10, "عشره": 10,
}

COUNT_NOUNS = {
    "pesticides": {"مبيد", "مبيدات", "متبقي", "متبقيات", "pesticide", "pesticides"},
    "places": {"حي", "احياء", "بلديه", "بلديات", "منشاه", "منشات", "منشئات"},
    "products": {"منتج", "منتجات", "صنف", "اصناف", "عينه", "عينات"},
    "periods": {"يوم", "ايام", "اسبوع", "اسابيع", "شهر", "شهور", "اشهر", "سنه", "سنوات", "عام", "اعوام"},
}
ALL_COUNT_NOUNS = set().union(*COUNT_NOUNS.values())


_CONNECTORS = {"و", "او", "or", "and", "-", "،", ","}
_EMPHATIC = {"ولو", "لو", "حتي"}


def number_value(word: str) -> Optional[int]:
    """Integer for a digit string or number word, allowing ال and a one-letter
    prefix: "الخمسة", "بثلاثة" (with three), "و٢"."""
    for w in (word, _strip_clitics(word), word[1:] if word[:1] in "وبلفك" else None):
        if not w:
            continue
        if w.isdigit():
            return int(w)
        if w in _NUMBER_WORDS:
            return _NUMBER_WORDS[w]
    return None


def count_for_nouns(text: str, nouns: Iterable[str] = ALL_COUNT_NOUNS) -> List[int]:
    """Numbers (digits or words, with or without ال) that directly quantify one
    of `nouns`: "خمس أحياء", "٥ أحياء", "الأحياء الخمسة", "مبيد واحد".
    "الحد الآمن الواحد" / "ولو مرة واحدة" quantify no count noun → [].
    Numbers joined by و before a noun count too: "١ و ٢ و ٣ مبيدات"."""
    nouns = {norm(n) for n in nouns}
    toks = tokens(text)
    bare = [_strip_clitics(t) for t in toks]
    found: List[int] = []
    used: set = set()          # a number word quantifies one noun only
    for i, noun in enumerate(bare):
        if noun not in nouns and toks[i] not in nouns:
            continue
        if i and toks[i - 1] in _EMPHATIC:      # "ولو عينة واحدة" = "even one", not N=1
            continue
        # number(s) before the noun, allowing "N و M" / "N أو M" chains
        j, before = i - 1, []
        while j >= 0:
            t = toks[j]
            if t in _CONNECTORS:
                j -= 1
                continue
            v = number_value(t) if j not in used else None
            if v is None:
                break
            before.append(v)
            used.add(j)
            j -= 1
        if before:
            found.extend(reversed(before))
            continue
        # number after the noun: "مبيد واحد", "الأحياء الخمسة"
        if i + 1 < len(toks) and i + 1 not in used:
            v = number_value(toks[i + 1])
            if v is not None:
                found.append(v)
                used.add(i + 1)
    return found


# ── Relative periods ─────────────────────────────────────────────────────────
_UNITS = {
    "يوم": "day", "ايام": "day", "اسبوع": "week", "اسابيع": "week",
    "شهر": "month", "شهور": "month", "اشهر": "month",
    "سنه": "year", "سنوات": "year", "عام": "year", "اعوام": "year",
    "day": "day", "days": "day", "week": "week", "weeks": "week",
    "month": "month", "months": "month", "year": "year", "years": "year",
}
_PLURAL_UNITS = {"ايام", "اسابيع", "شهور", "اشهر", "سنوات", "اعوام", "days", "weeks", "months", "years"}
_DUALS = {"يومين": ("day", 2), "اسبوعين": ("week", 2), "شهرين": ("month", 2),
          "سنتين": ("year", 2), "عامين": ("year", 2)}
_LAST_BEFORE = {"اخر", "last"}
_LAST_AFTER = {"اخير", "اخيره", "ماضي", "ماضيه", "فائت", "فائته", "سابق", "سابقه"}
_PERIOD_MARKERS = _LAST_BEFORE | _LAST_AFTER | {"خلال", "امس"}


def parse_period(text: str) -> Optional[Tuple[int, str]]:
    """(n, unit) for a relative period, or None. Accepts the unit before or
    after its number and marker: "آخر ٣ شهور", "آخر ثلاث شهور",
    "الأشهر الثلاثة الأخيرة", "الشهر الماضي", "خلال الشهرين الماضيين".
    A plural unit with no number ("الأشهر الأخيرة") is ambiguous → None."""
    toks = tokens(text)
    bare = [_strip_clitics(t) for t in toks]
    for b in bare:
        if b in _DUALS:
            unit, n = _DUALS[b]
            return n, unit
    if "امس" in bare:
        return 1, "day"
    for i, b in enumerate(bare):
        unit = _UNITS.get(b)
        if not unit:
            continue
        window_before = bare[max(0, i - 2):i]
        window_after = bare[i + 1:i + 3]
        has_marker = (any(w in _LAST_BEFORE for w in window_before)
                      or any(w in _LAST_AFTER for w in window_after))
        if not has_marker:
            continue
        n = None
        for w in (toks[i - 1] if i else "", toks[i + 1] if i + 1 < len(toks) else ""):
            v = number_value(w) if w else None
            if v is not None:
                n = v
                break
        if n is None:
            if b in _PLURAL_UNITS:
                return None           # "الأشهر الأخيرة" — how many?
            n = 1                     # "الشهر الماضي", "آخر شهر"
        if n > 0:
            return n, unit
    return None


def has_period_phrase(text: str) -> bool:
    """True when the question talks about a relative period (a time unit next
    to آخر / الأخيرة / الماضي / خلال …), whether or not it parses."""
    bare = [_strip_clitics(t) for t in tokens(text)]
    for i, b in enumerate(bare):
        if b in _DUALS:
            return True
        if b in _UNITS:
            near = bare[max(0, i - 2):i] + bare[i + 1:i + 3]
            if any(w in _PERIOD_MARKERS for w in near):
                return True
    return False
