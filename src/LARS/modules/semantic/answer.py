"""
Answer a QuerySpec: validate -> SQL -> Arabic text + DataFrame.

Every answer opens with "فهمت سؤالك كالتالي: …" so the user can check what
was computed. Category answers say "(حسب تصنيف المختبر)". The technical
metric is "تجاوزت الحد الأقصى الأوروبي (EU MRL)", never "مخالفة".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import pandas as pd

from modules.semantic.catalog import Catalog
from modules.semantic.query_spec import (
    ANALYTE_METRICS, COUNT_METRICS, RATE_METRICS, GroupBy, Metric, PeriodType, QuerySpec, Scope, Sort,
)
from modules.semantic.sql_builder import MAIN_COLUMN, MIN_RATE_SAMPLES, NoMatchingSamples, run
from modules.semantic.validator import ResolvedSpec, SpecRejected, validate

LAB_CATEGORY = "(حسب تصنيف المختبر)"
EU_MRL = "تجاوزت الحد الأقصى الأوروبي (EU MRL)"
OFFICIAL = "(حسب النتيجة الرسمية للمختبر)"
TEXT_ROWS = 10

CATEGORY_AR = {
    "Vegetables": "الخضروات", "Fruits": "الفواكه", "Spices": "التوابل", "Nuts": "المكسرات",
    "Grains": "الحبوب", "Leafy Greens": "الورقيات", "Dates": "التمور ومنتجاتها",
    "Raw": "Raw", "Ready Foods": "Ready Foods",
}
GROUP_AR = {GroupBy.category: "التصنيف", GroupBy.product: "المنتج", GroupBy.municipality: "البلدية",
            GroupBy.neighborhood: "الحي", GroupBy.month: "الشهر"}
MONTHS_AR = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو",
             "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
UNIT_AR = {  # (1, 2, 3–10, 11+)
    "day": ("يوم", "يومين", "أيام", "يوماً"), "week": ("أسبوع", "أسبوعين", "أسابيع", "أسبوعاً"),
    "month": ("شهر", "شهرين", "أشهر", "شهراً"), "year": ("سنة", "سنتين", "سنوات", "سنة"),
}
METRIC_COLUMNS = {
    Metric.sample_count: ["samples"],
    Metric.noncompliant_count: ["samples", "non_compliant"],
    Metric.noncompliance_rate: ["samples", "non_compliant", "rate_pct"],
    Metric.above_limit_sample_count: ["samples", "above_limit_samples"],
    Metric.above_limit_rate: ["samples", "above_limit_samples", "rate_pct"],
}


@dataclass
class SemanticAnswer:
    ok: bool
    text: str
    df: Optional[pd.DataFrame] = None
    resolved: Optional[ResolvedSpec] = None
    info: dict = field(default_factory=dict)


def _n(x) -> str:
    return f"{int(x):,}"


COMPOUNDS = "المركّبات المكتشفة (مبيدات وسموم فطرية)"
AMONG_DETECTED = "من بين المركّبات التي ظهرت في البيانات"


def _above_phrase(k: Optional[float]) -> str:
    """'تجاوزت الحد الأقصى الأوروبي (EU MRL)', or with a multiple
    'تجاوزت 2 أضعاف الحد الأقصى الأوروبي (EU MRL)'. Never violation wording."""
    return EU_MRL if not k or k == 1 else f"تجاوزت {k:g} أضعاف الحد الأقصى الأوروبي (EU MRL)"


def _metric_phrase(r: ResolvedSpec, mixed: bool = False) -> str:
    """`mixed`: the listed analytes include mycotoxins, so they are not all 'مبيدات'."""
    s = r.spec
    above = _above_phrase(s.mrl_multiple)
    most = "أقل" if s.sort is Sort.asc else "أكثر"
    return {
        Metric.sample_count: "عدد العينات",
        Metric.noncompliant_count: f"عدد العينات غير المطابقة {OFFICIAL}",
        Metric.noncompliance_rate: f"نسبة العينات غير المطابقة {OFFICIAL}",
        Metric.above_limit_sample_count: f"عدد العينات التي {above}",
        Metric.above_limit_rate: f"نسبة العينات التي {above}",
        Metric.top_pesticides: (f"{most} {s.top_n} من {COMPOUNDS} ظهوراً (حسب عدد العينات)" if mixed
                                else f"{most} {s.top_n} مبيدات ظهوراً (حسب عدد العينات)"),
        Metric.pesticide_list: COMPOUNDS if mixed else "المبيدات التي ظهرت",
        Metric.never_detected_list: (f"{'المركّبات (مبيدات وسموم فطرية)' if mixed else 'المبيدات'} "
                                     f"التي لم تظهر أبداً، {AMONG_DETECTED}"),
    }[s.metric]


def _period_phrase(r: ResolvedSpec) -> Optional[str]:
    p = r.spec.period
    if r.period is None:
        return None
    lo, hi = r.period
    if p.type is PeriodType.relative:
        forms = UNIT_AR[p.unit.value]
        span = {1: forms[0], 2: forms[1]}.get(p.n) or f"{p.n} {forms[2] if p.n <= 10 else forms[3]}"
        return f"خلال آخر {span} من البيانات ({lo} إلى {hi})"
    if p.type is PeriodType.absolute_month:
        return f"في شهر {MONTHS_AR[lo.month - 1]} {lo.year}"
    return f"من {lo} إلى {hi}"


def _scope_parts(r: ResolvedSpec) -> List[str]:
    parts = []
    if r.spec.scope is Scope.non_compliant:
        parts.append("في العينات غير المطابقة")
    if r.categories:
        parts.append("في " + "، ".join(CATEGORY_AR.get(c, c) for c in r.categories) + f" {LAB_CATEGORY}")
    if r.products:
        asked = "، ".join(r.terms.get("product", [])) or "المنتجات"
        parts.append(f"للمنتج: {asked} ({'، '.join(r.products)})")
    if r.municipalities:
        parts.append("في " + "، ".join(r.municipalities))
    if r.neighborhoods:
        parts.append("في حي " + "، ".join(r.neighborhoods))
    if r.pesticides:
        verb = "تجاوز فيها الحدَّ" if r.spec.metric in (Metric.above_limit_sample_count, Metric.above_limit_rate) else "ظهر فيها"
        parts.append(f"التي {verb}: {'، '.join(r.pesticides)}")
    period = _period_phrase(r)
    if period:
        parts.append(period)
    return parts


def describe(r: ResolvedSpec, mixed: bool = False) -> str:
    parts = [_metric_phrase(r, mixed)] + _scope_parts(r)
    if r.spec.group_by:
        by = f"موزعة حسب {GROUP_AR[r.spec.group_by]}"
        if r.spec.group_by is GroupBy.category and not r.categories:
            by += f" {LAB_CATEGORY}"
        parts.append(by)
    return "فهمت سؤالك كالتالي: " + "، ".join(parts) + "."


def _value_line(m: Metric, row) -> str:
    if m is Metric.sample_count:
        return f"{_n(row.samples)} عينة"
    if m is Metric.noncompliant_count:
        return f"{_n(row.non_compliant)} عينة غير مطابقة من أصل {_n(row.samples)}"
    if m is Metric.above_limit_sample_count:
        return f"{_n(row.above_limit_samples)} عينة من أصل {_n(row.samples)}"
    num = row.non_compliant if m is Metric.noncompliance_rate else row.above_limit_samples
    return f"{row.rate_pct:.1f}% ({_n(num)} من {_n(row.samples)} عينة)"


def _group_label(g: GroupBy, value) -> str:
    return CATEGORY_AR.get(value, value) if g is GroupBy.category else str(value)


def _columns(df: pd.DataFrame, m: Metric, keep_grp: bool) -> pd.DataFrame:
    cols = (["grp"] if keep_grp else []) + METRIC_COLUMNS[m]
    out = df[cols].copy()
    for c in ("samples", "non_compliant", "above_limit_samples"):
        if c in out:
            out[c] = out[c].astype("int64")
    return out


def _format(r: ResolvedSpec, df: pd.DataFrame, total: Optional[pd.DataFrame], info: dict):
    s, m = r.spec, r.spec.metric
    if "samples_above_limit" in df:
        df = df.astype({"samples_above_limit": "int64"})
    mixed = m in ANALYTE_METRICS and bool((df["analyte_class"] == "mycotoxin").any())
    lines = [describe(r, mixed)]
    if m in ANALYTE_METRICS:
        if m is Metric.never_detected_list:
            lines.append(f"النتيجة: {_n(len(df))} مركّباً لم يظهر في النطاق المطلوب، {AMONG_DETECTED} "
                         "(البيانات تسجّل المركّبات المكتشفة فقط، والأسماء موحّدة حسب جدول أسماء المبيدات).")
            lines += [f"• {p}" for p in df["pesticide"].head(TEXT_ROWS)]
        elif df.empty:
            lines.append("النتيجة: لم يظهر أي مبيد في العينات المطابقة للشروط.")
        else:
            lines.append(f"النتيجة ({_n(info['matching_samples'])} عينة مطابقة للشروط):")
            lines += [f"{i}. {row.pesticide} — ظهر في {_n(row.samples_detected)} عينة، "
                      f"منها {_n(row.samples_above_limit)} {EU_MRL}"
                      for i, row in enumerate(df.head(TEXT_ROWS).itertuples(), 1)]
        if len(df) > TEXT_ROWS:
            lines.append(f"… والباقي في الجدول ({_n(len(df))} صفاً).")
        return "\n".join(lines), df.reset_index(drop=True)

    if not s.group_by:
        lines.append("النتيجة: " + _value_line(m, df.iloc[0]) + ".")
        return "\n".join(lines), _columns(df, m, keep_grp=False)

    g = s.group_by
    for row in df.head(TEXT_ROWS).itertuples():
        lines.append(f"• {_group_label(g, row.grp)}: {_value_line(m, row)}")
    if len(df) > TEXT_ROWS:
        lines.append(f"… والباقي في الجدول ({_n(len(df))} صفاً).")
    total_row = total.iloc[0]
    lines.append(f"الإجمالي: {_value_line(m, total_row)}.")
    if info.get("groups_below_threshold"):
        lines.append(f"(استُبعدت {_n(info['groups_below_threshold'])} مجموعة لديها أقل من "
                     f"{MIN_RATE_SAMPLES} عينات من ترتيب النسب.)")
    if g is GroupBy.category:
        lines.append("ملاحظة: بعض العينات مسجلة تحت أكثر من تصنيف، فتُحتسب في كل تصنيف منها.")
    out = _columns(df, m, keep_grp=True)
    if m in COUNT_METRICS:
        out["share_pct"] = (100.0 * out[MAIN_COLUMN[m]] / total_row[MAIN_COLUMN[m]]).round(1) \
            if total_row[MAIN_COLUMN[m]] else 0.0
    tot = _columns(total, m, keep_grp=True)
    tot["grp"] = "الإجمالي"
    if m in COUNT_METRICS:
        tot["share_pct"] = 100.0
    out = pd.concat([out, tot], ignore_index=True).rename(columns={"grp": g.value})
    return "\n".join(lines), out


def answer_spec(spec: QuerySpec, catalog: Catalog, resolver, db_path: str) -> SemanticAnswer:
    try:
        r = validate(spec, catalog, resolver)
    except SpecRejected as e:
        return SemanticAnswer(False, str(e))
    try:
        df, total, info = run(r, catalog, db_path)
    except NoMatchingSamples:
        where = "، ".join(_scope_parts(r)) or "الشروط المطلوبة"
        return SemanticAnswer(False, f"⚠️ لم تطابق أي عينة هذه الشروط: {where}.", resolved=r)
    text, out = _format(r, df, total, info)
    return SemanticAnswer(True, text, out, r, info)
