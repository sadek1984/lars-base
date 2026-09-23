"""
entity_resolver.py — resolve question entities to values that exist in the DB.

Handlers used to match free-text entities literally against chemistry_tidy,
but the DB stores different surface forms (English product/category names,
'بلدية '-prefixed municipalities). EntityResolver loads the real DISTINCT
values once, plus the checked-in alias vocabulary (entity_aliases.csv), and
resolves a question by scanning its normalized words for known values —
never by slicing text around keywords.

Every value it returns is an exact DB value, so handlers can filter with
`"col" IN (?, ...)` parameters.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

from modules.query.mappings import (
    PESTICIDE_VARIANTS,
    SAMPLE_CORRECTIONS,
    normalize_arabic_text,
)

ALIASES_CSV = Path(__file__).with_name("entity_aliases.csv")

# Clitic prefixes stripped when comparing a question word to a vocabulary word:
# و (and), ب/ل/ك/ف (prepositions), ال (article), لل (ل + ال).
_PREFIXES = ("وال", "بال", "لل", "فال", "كال", "ال", "و", "ب", "ل")
_PUNCT_RE = re.compile(r"[؟?،,.!:;()\[\]\"'«»]")
_ALL_MUNICIPALITIES = (("كل", "بلديه"), ("كل", "بلديات"), ("حسب", "بلديه"), ("لكل", "بلديه"))


def _stems(word: str) -> Set[str]:
    """All forms of a normalized word with one clitic prefix removed."""
    out = {word}
    for p in _PREFIXES:
        if word.startswith(p) and len(word) - len(p) >= 2:
            out.add(word[len(p):])
    return out


def _key(text: str) -> Tuple[str, ...]:
    """Vocabulary phrase -> tuple of normalized words with a leading ال removed."""
    words = _PUNCT_RE.sub(" ", normalize_arabic_text(text).lower()).split()
    return tuple(w[2:] if w.startswith("ال") and len(w) > 3 else w for w in words)


def _en_tokens(value: str) -> Tuple[str, ...]:
    """English DB value -> lowercase tokens with a trailing plural 's' folded."""
    toks = re.findall(r"[a-z]+", value.lower())
    return tuple(t[:-1] if len(t) > 3 and t.endswith("s") and not t.endswith("ss") else t
                 for t in toks)


def canonical_pesticide(name: str) -> str:
    """Map a DB pesticide spelling to its canonical name via PESTICIDE_VARIANTS."""
    low = (name or "").strip().lower()
    return _VARIANT_TO_CANONICAL.get(low, low)


_VARIANT_TO_CANONICAL = {v.lower(): k for k, vs in PESTICIDE_VARIANTS.items() for v in vs}


@dataclass
class Resolution:
    products: List[str] = field(default_factory=list)
    product_terms_unresolved: List[str] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)
    category_terms: List[str] = field(default_factory=list)
    municipalities: List[str] = field(default_factory=list)
    all_municipalities: bool = False
    mentions_municipality: bool = False
    pesticide_group: Optional[str] = None
    consumed: Set[int] = field(default_factory=set)   # word indices claimed by products


class EntityResolver:
    def __init__(self, con, aliases_csv: Path = ALIASES_CSV):
        rows = con.execute(
            'SELECT DISTINCT "اسم العينة", "نوع العينة" FROM chemistry_tidy '
            'WHERE "اسم العينة" IS NOT NULL'
        ).fetchall()
        self.products: List[str] = sorted({r[0] for r in rows})
        self.product_tokens: Dict[str, Tuple[str, ...]] = {p: _en_tokens(p) for p in self.products}
        self.db_categories: Set[str] = {r[1] for r in rows if r[1]}
        self.db_municipalities: List[str] = [r[0] for r in con.execute(
            'SELECT DISTINCT "اسم البلدية" FROM chemistry_tidy WHERE "اسم البلدية" IS NOT NULL'
        ).fetchall()]
        pesticides = [r[0] for r in con.execute(
            "SELECT DISTINCT pesticide_name FROM chemistry_tidy "
            "WHERE pesticide_name NOT IN ('NO DETECTION', 'NO DATA')"
        ).fetchall()]

        vocab: Dict[str, List[Tuple[str, str]]] = {}
        with open(aliases_csv, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                vocab.setdefault(r["vocabulary"], []).append((r["raw_term"], r["resolved_value"]))

        self.category_keys = {_key(t): v for t, v in vocab.get("sample_category", [])
                              if v in self.db_categories}
        self.category_label: Dict[str, str] = {}
        for t, v in vocab.get("sample_category", []):
            if v in self.db_categories and t.startswith("ال"):
                self.category_label.setdefault(v, t)
        self.alias_keys: Dict[Tuple[str, ...], List[str]] = {}
        for t, v in vocab.get("product_alias", []):
            if v in self.product_tokens:
                self.alias_keys.setdefault(_key(t), []).append(v)
        self.head_keys = {_key(t): v for t, v in vocab.get("product_head", [])}
        self.head_tokens = set(self.head_keys.values())
        self.qualifier_keys = {_key(t)[0]: v for t, v in vocab.get("product_qualifier", [])}
        self.group_keys = {_key(t): v for t, v in vocab.get("pesticide_group", [])}
        self.sample_keys = {_key(k): v for k, v in SAMPLE_CORRECTIONS.items() if _key(k)}

        # Municipality keys: the stored name without its 'بلدية' prefix word.
        # Single-word keys (e.g. 'الرس') only count when the question says بلدية.
        self.municipality_keys: Dict[Tuple[str, ...], str] = {}
        for m in self.db_municipalities:
            k = tuple(w for w in _key(m) if w != "بلديه")
            if k:
                self.municipality_keys[k] = m
            if k and k[-1] == "فرعيه" and len(k) > 1:
                self.municipality_keys.setdefault(k[:-1], m)

        from modules.data.pesticide_groups import classify_pesticide
        self.group_pesticides: Dict[str, List[str]] = {}
        for p in pesticides:
            self.group_pesticides.setdefault(classify_pesticide(canonical_pesticide(p)), []).append(p)

    # ── matching primitives ────────────────────────────────────────────────
    @staticmethod
    def _words(question: str) -> List[str]:
        return [_PUNCT_RE.sub("", normalize_arabic_text(w).lower()) for w in question.split()]

    @staticmethod
    def _match_at(stems: List[Set[str]], i: int, key: Tuple[str, ...]) -> bool:
        return i + len(key) <= len(stems) and all(key[j] in stems[i + j] for j in range(len(key)))

    def _longest(self, stems, i, keys) -> Tuple[int, Optional[str]]:
        best_len, best_val = 0, None
        for k, v in keys.items():
            if len(k) > best_len and self._match_at(stems, i, k):
                best_len, best_val = len(k), v
        return best_len, best_val

    def products_for_tokens(self, required: Sequence[str]) -> List[str]:
        """DB products whose tokens contain all `required` tokens. A product whose
        head noun (last token) is a different known product head is excluded, so
        'orange' does not pull in 'Sweet Orange Pepper'."""
        req = set(required)
        out = []
        for p, toks in self.product_tokens.items():
            if not toks or not req <= set(toks):
                continue
            head = toks[-1]
            if head in self.head_tokens and head not in req:
                continue
            out.append(p)
        return out

    # ── public API ─────────────────────────────────────────────────────────
    def resolve(self, question: str) -> Resolution:
        res = Resolution()
        words = self._words(question)
        stems = [_stems(w) for w in words]
        flat = {s for st in stems for s in st}

        i = 0
        while i < len(words):
            if not words[i]:
                i += 1
                continue
            # Candidates starting here: explicit CSV alias, generic head + qualifiers,
            # SAMPLE_CORRECTIONS phrase. Longest span wins; ties prefer alias, then head
            # (both DB-derived) over the legacy phrase map.
            candidates = []
            a_len, alias_vals = self._longest(stems, i, self.alias_keys)
            if alias_vals:
                candidates.append((a_len, 2, list(range(i, i + a_len)), list(alias_vals)))
            h_len, head = self._longest(stems, i, self.head_keys)
            if head:
                span, required = self._head_span(words, stems, i, h_len, head)
                candidates.append((len(span), 1, span, self.products_for_tokens(required)))
            else:
                # English word order puts qualifiers first: 'green sweet pepper'.
                j = i
                while j < len(words) and words[j].isascii() and words[j] in self.qualifier_keys:
                    j += 1
                if j > i:
                    h_len, head = self._longest(stems, j, self.head_keys)
                    if head:
                        span, required = self._head_span(words, stems, j, h_len, head)
                        candidates.append((len(span), 1, span, self.products_for_tokens(required)))
            s_len, target = self._longest(stems, i, self.sample_keys)
            if target:
                candidates.append((s_len, 0, list(range(i, i + s_len)),
                                   self.products_for_tokens(_en_tokens(target))))
            if not candidates:
                i += 1
                continue
            _, _, span, matched = max(candidates, key=lambda c: (c[0], c[1]))
            if matched:
                res.products.extend(p for p in matched if p not in res.products)
            else:
                res.product_terms_unresolved.append(" ".join(question.split()[span[0]:span[-1] + 1]))
            res.consumed.update(span)
            i = span[-1] + 1

        says_baladiya = "بلديه" in flat or "بلديات" in flat
        for i in range(len(words)):
            c_len, cat = self._longest(stems, i, self.category_keys)
            if cat and cat not in res.categories:
                res.categories.append(cat)
                res.category_terms.append(" ".join(question.split()[i:i + c_len]))
            _, grp = self._longest(stems, i, self.group_keys)
            if grp and not res.pesticide_group:
                res.pesticide_group = grp
            m_len, mun = self._longest(stems, i, self.municipality_keys)
            if mun and mun not in res.municipalities and (m_len > 1 or says_baladiya):
                res.municipalities.append(mun)
        res.mentions_municipality = says_baladiya
        res.all_municipalities = any(
            self._match_at(stems, i, k) for i in range(len(words)) for k in _ALL_MUNICIPALITIES
        )
        return res

    def _head_span(self, words, stems, i, h_len, head) -> Tuple[List[int], List[str]]:
        """Head word(s) plus adjacent qualifiers: after the head for Arabic,
        before it for English ('green sweet pepper')."""
        span, required = list(range(i, i + h_len)), [head]
        is_arabic = any("؀" <= c <= "ۿ" for c in words[i])
        if is_arabic:
            j = i + h_len
            while j < len(words) and len(span) < h_len + 3:
                q = next((self.qualifier_keys[s] for s in stems[j] if s in self.qualifier_keys), None)
                if not q:
                    break
                required.append(q)
                span.append(j)
                j += 1
        else:
            j = i - 1
            while j >= 0 and words[j] in self.qualifier_keys:
                required.append(self.qualifier_keys[words[j]])
                span.insert(0, j)
                j -= 1
        return span, required

    def mask_consumed(self, question: str, res: Resolution) -> str:
        """Question text with product/qualifier words blanked, so e.g. the
        qualifier 'الأخضر' is never read as the neighborhood 'الأخضر'."""
        parts = question.split()
        return " ".join(" " * len(w) if idx in res.consumed else w for idx, w in enumerate(parts))

    def category_db_value(self, key: Optional[str]) -> Optional[str]:
        """Legacy category key ('spice', 'Spices', 'التوابل') -> DB category value."""
        if not key:
            return None
        if key in self.db_categories:
            return key
        return self.category_keys.get(_key(key))

    def label_for_category(self, db_value: str) -> str:
        return self.category_label.get(db_value, db_value)

    def pesticides_in_group(self, group: str) -> List[str]:
        return sorted(self.group_pesticides.get(group, []))
