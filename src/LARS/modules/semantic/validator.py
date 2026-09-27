"""
Validate a QuerySpec against the Catalog: every filter word is resolved to
exact DB values, or the spec is rejected with a message that names the word.
Nothing is guessed: an unknown value is a refusal, never a dropped filter.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date
from typing import Dict, List, Optional, Tuple

from modules.query.mappings import PESTICIDE_AR_TO_EN_NORM, normalize_neighborhood
from modules.query.text_norm import _strip_clitics, has_period_phrase, norm, tokens
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
    highlight: Optional[str] = None               # "X compared with all": the one value of the grouped dimension
    added_from_question: Tuple[str, ...] = ()     # categories the coverage check added

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
    if spec.metric in (Metric.top_pesticides, Metric.never_detected_list) and spec.group_by is not None:
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
    # Grouping by a dimension filtered to ONE value ("spices, by category") is
    # a comparison with everything else ("spices vs the overall rate"): drop
    # that filter so every group and the distinct total are shown, and put
    # the asked value first.
    highlight = None
    dims = {GroupBy.category: cats, GroupBy.product: prods, GroupBy.municipality: muns,
            GroupBy.neighborhood: hoods}
    if spec.group_by in dims and len(dims[spec.group_by]) == 1:
        if spec.metric in ANALYTE_METRICS:
            # "pesticides in cardamom, by product": one group → a plain list
            spec = spec.model_copy(update={"group_by": None})
        else:
            highlight = dims[spec.group_by][0]
            dims[spec.group_by].clear()
    raw = tuple(r for p in pests for r in catalog.analytes.raw_names(p))
    return ResolvedSpec(
        spec=spec, categories=tuple(sorted(cats)), products=tuple(sorted(prods)),
        municipalities=tuple(sorted(muns)), neighborhoods=tuple(sorted(hoods)),
        pesticides=tuple(pests), pesticide_raw=tuple(sorted(raw)), period=period,
        terms={k: list(v) for k, v in f.model_dump().items() if v}, highlight=highlight,
    )


# ── Coverage: the spec must not drop what the question names ─────────────────

_MONTHS = ["يناير", "فبراير", "مارس", "ابريل", "مايو", "يونيو", "يوليو", "اغسطس",
           "سبتمبر", "اكتوبر", "نوفمبر", "ديسمبر"]


def _question_categories(question: str, catalog: Catalog) -> set:
    words = [_strip_clitics(w) for w in tokens(question)]
    found, used = set(), set()
    for n in (2, 1):                      # 'خضار ورقية' is Leafy Greens, not also Vegetables
        for i in range(len(words) - n + 1):
            span = set(range(i, i + n))
            hit = None if span & used else catalog.category_terms.get(category_key(" ".join(words[i:i + n])))
            if hit:
                found.update(hit)
                used |= span
    return found


def check_coverage(question: str, r: ResolvedSpec, catalog: Catalog, resolver) -> ResolvedSpec:
    """Refuse a spec that silently drops a category, product, municipality,
    pesticide or period the question names — the LLM must never broaden.
    One repair: a spec with no category and no product at all gets the
    category words the question names (from the reviewed table); that can
    only narrow the answer. Returns the (possibly repaired) spec."""
    g = r.spec.group_by
    in_scope_cats = set(r.categories) | ({r.highlight} if g is GroupBy.category and r.highlight else set())
    if g is not GroupBy.category:
        missing = _question_categories(question, catalog) - in_scope_cats
        if missing and not r.categories and not r.products and r.highlight is None:
            r = replace(r, categories=tuple(sorted(missing)), added_from_question=tuple(sorted(missing)))
            in_scope_cats = set(r.categories)
        elif missing and not (set(r.products) and all(
                set(catalog.product_categories.get(p, ())) & missing for p in r.products)):
            raise SpecRejected(f"coverage: category {sorted(missing)} dropped")
    res = resolver.resolve(question)
    kept_products = set(r.products) | ({r.highlight} if g is GroupBy.product and r.highlight else set())
    named = [p for p in res.products
             if not set(catalog.product_categories.get(p, ())) & in_scope_cats]   # 'المكسرات' → Mixed Nuts
    if named and g is not GroupBy.product and not set(named) & kept_products:
        raise SpecRejected(f"coverage: product {named} dropped")
    if res.municipalities and g is not GroupBy.municipality and not set(res.municipalities) <= (
            set(r.municipalities) | ({r.highlight} if r.highlight else set())):
        raise SpecRejected(f"coverage: municipality {res.municipalities} dropped")
    if r.spec.metric not in ANALYTE_METRICS:
        from modules.query.mappings import detect_pesticide
        named_p = detect_pesticide(question)
        if named_p:
            canon = catalog.analytes.raw_to_canonical.get(named_p) or named_p.lower()
            if canon not in r.pesticides:
                raise SpecRejected(f"coverage: pesticide {named_p} dropped")
    months = {m for m in _MONTHS if m in norm(question).replace("أ", "ا").replace("إ", "ا")}
    # "من شهر إلى آخر" with group_by month is a trend, not a period.
    phrase = has_period_phrase(question) and g is not GroupBy.month
    if (phrase or months) and r.period is None:
        raise SpecRejected("coverage: period dropped")
    return r
