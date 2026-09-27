"""
Validate a QuerySpec against the Catalog: every filter word is resolved to
exact DB values, or the spec is rejected with a message that names the word.
Nothing is guessed: an unknown value is a refusal, never a dropped filter.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Tuple

from modules.query.mappings import PESTICIDE_AR_TO_EN_NORM, normalize_neighborhood
from modules.query.text_norm import norm
from modules.semantic.catalog import Catalog
from modules.semantic.query_spec import (
    ANALYTE_METRICS, RATE_METRICS, GroupBy, Metric, QuerySpec, Scope,
)
from modules.semantic.tables import category_key

_AFLATOXIN_WORDS = {"aflatoxin", "aflatoxins", "افلاتوكسين", "افلاتوكسينات"}


class SpecRejected(Exception):
    """The spec cannot be answered; str(e) is the Arabic message for the user."""


@dataclass(frozen=True)
class ResolvedSpec:
    spec: QuerySpec
    categories: Tuple[str, ...] = ()
    products: Tuple[str, ...] = ()
    municipalities: Tuple[str, ...] = ()
    neighborhoods: Tuple[str, ...] = ()
    pesticides: Tuple[str, ...] = ()              # canonical analytes
    pesticide_raw: Tuple[str, ...] = ()           # their stored spellings (SQL IN list)
    period: Optional[Tuple[date, date]] = None
    terms: Dict[str, List[str]] = field(default_factory=dict)  # filter -> words as asked

    @property
    def mentions_category(self) -> bool:
        return bool(self.categories) or self.spec.group_by is GroupBy.category


def _add(out: List[str], values) -> None:
    out.extend(v for v in values if v not in out)


def _strip_al(word: str) -> str:
    return word[2:] if word.startswith("ال") and len(word) > 3 else word


def _category(term: str, catalog: Catalog) -> Optional[Tuple[str, ...]]:
    hit = catalog.category_terms.get(category_key(term))
    if hit:
        return hit
    stored = {c.lower(): c for c in catalog.categories}
    return (stored[term.strip().lower()],) if term.strip().lower() in stored else None


def _exact(term: str, values) -> Optional[str]:
    by_norm = {norm(v): v for v in values}
    return by_norm.get(norm(term))


def _neighborhood(term: str, catalog: Catalog) -> Optional[str]:
    t = norm(term)
    for prefix in ("حي ", "حى "):
        if t.startswith(prefix):
            t = t[len(prefix):]
    t = normalize_neighborhood(t)
    by_key = {_strip_al(norm(v)): v for v in catalog.neighborhoods}
    return by_key.get(_strip_al(norm(t)))


def _pesticides(term: str, catalog: Catalog) -> List[str]:
    a = catalog.analytes
    t = term.strip()
    low = t.lower()
    if low in _AFLATOXIN_WORDS or norm(_strip_al(norm(t))) in _AFLATOXIN_WORDS:
        return [c for c in a.canonical_names if c.startswith("aflatoxin")]
    canon = {c.lower(): c for c in a.canonical_names}
    if low in canon:
        return [canon[low]]
    raw = {r.lower(): c for r, c in a.raw_to_canonical.items()}
    if raw.get(low):
        return [raw[low]]
    en = PESTICIDE_AR_TO_EN_NORM.get(norm(t))            # exact Arabic dictionary, no fuzzy
    if en and (canon.get(en.lower()) or raw.get(en.lower())):
        return [canon.get(en.lower()) or raw[en.lower()]]
    return []


_REJECT = {
    "category": "لم أتعرف على التصنيف «{}»",
    "product": "لم أجد المنتج «{}» في بيانات المختبر",
    "municipality": "لم أجد البلدية «{}» في بيانات المختبر",
    "neighborhood": "لم أجد الحي «{}» في بيانات المختبر",
    "pesticide": "لم أجد المبيد «{}» في بيانات المختبر",
}


def validate(spec: QuerySpec, catalog: Catalog, resolver) -> ResolvedSpec:
    if spec.unsupported:
        raise SpecRejected(f"⚠️ لا يمكنني الإجابة عن هذا السؤال: {spec.reason}")
    if spec.scope is Scope.non_compliant and spec.metric in RATE_METRICS:
        raise SpecRejected("⚠️ لا يمكن حساب نسبة داخل العينات غير المطابقة فقط.")
    if spec.metric in ANALYTE_METRICS and spec.filters.pesticide:
        raise SpecRejected("⚠️ قائمة المبيدات لا تُصفّى بمبيد محدد؛ اسأل عن عدد العينات التي ظهر فيها المبيد.")
    if spec.metric in ANALYTE_METRICS and spec.group_by is not None:
        raise SpecRejected("⚠️ ترتيب المبيدات حسب مجموعة (مثل كل بلدية) غير مدعوم حالياً.")

    f = spec.filters
    cats: List[str] = []
    prods: List[str] = []
    for t in f.category:
        hit = _category(t, catalog)
        if not hit:
            raise SpecRejected("⚠️ " + _REJECT["category"].format(t) + ".")
        _add(cats, hit)
    for t in f.product:
        hit = _category(t, catalog)          # 'المكسرات' as a product means the category
        if hit:
            _add(cats, hit)
            continue
        res = resolver.resolve(t)
        exact = _exact(t, catalog.products)
        found = list(res.products) or ([exact] if exact else [])
        if not found:
            raise SpecRejected("⚠️ " + _REJECT["product"].format(t) + ".")
        _add(prods, found)
    muns: List[str] = []
    for t in f.municipality:
        res = resolver.resolve(t)
        found = list(res.municipalities) or [m for m in [_exact(t, catalog.municipalities)] if m]
        if not found:
            raise SpecRejected("⚠️ " + _REJECT["municipality"].format(t) + ".")
        _add(muns, found)
    hoods: List[str] = []
    for t in f.neighborhood:
        hit = _neighborhood(t, catalog)
        if not hit:
            raise SpecRejected("⚠️ " + _REJECT["neighborhood"].format(t) + ".")
        _add(hoods, [hit])
    pests: List[str] = []
    for t in f.pesticide:
        found = _pesticides(t, catalog)
        if not found:
            raise SpecRejected("⚠️ " + _REJECT["pesticide"].format(t) + ".")
        _add(pests, found)

    period = spec.period.bounds(catalog.max_date)
    if period and (period[1] < catalog.min_date or period[0] > catalog.max_date):
        raise SpecRejected(f"⚠️ الفترة المطلوبة خارج نطاق بيانات المختبر "
                           f"({catalog.min_date} إلى {catalog.max_date}).")
    raw = tuple(r for p in pests for r in catalog.analytes.raw_names(p))
    return ResolvedSpec(
        spec=spec, categories=tuple(sorted(cats)), products=tuple(sorted(prods)),
        municipalities=tuple(sorted(muns)), neighborhoods=tuple(sorted(hoods)),
        pesticides=tuple(pests), pesticide_raw=tuple(sorted(raw)), period=period,
        terms={k: list(v) for k, v in f.model_dump().items() if v},
    )
