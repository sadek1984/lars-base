"""
LARS :: poisoning query handler
===============================
Self-contained. Returns primitives — (text_ar, df, meta) — so it makes no
assumption about the engine's result class.

In core_query_engine.py you need one adapter block:

    if intent.name.startswith("POISONING_"):
        from modules.poisoning.handler import handle_poisoning
        text, df, meta = handle_poisoning(self.con, intent.name, entities)
        return text, df          # <- match YOUR engine's return shape here

meta carries {"render": ..., "disclaimer": ..., "intent": ...} if your UI
wants to pick a chart type; ignore it otherwise.
"""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from .intents import POISONING_INTENTS
from .router_gate import ENUM_NAME_INTENT


# ---------------------------------------------------------------------------
# Arabic answer formatting per intent
# ---------------------------------------------------------------------------

def _fmt_headline(df: pd.DataFrame) -> str:
    r = df.iloc[0]
    return (
        f"📊 **سجل حالات التسمم الغذائي**\n\n"
        f"- عدد الحالات المسجلة: **{int(r['incidents'])}**\n"
        f"- إجمالي المصابين: **{int(r['people_affected'])}**\n"
        f"- عدد قرارات الإدانة: **{int(r['convictions'])}**\n"
        f"- وسيط فترة الحضانة: **{r['median_incubation_h']:g} ساعة**\n"
        f"- أكبر تجمع إصابات: **{int(r['largest_cluster'])} مصاب**\n"
        f"- عدد البلديات المشمولة: **{int(r['municipalities'])}**\n"
        f"- تاريخ آخر حادثة: **{pd.to_datetime(r['last_incident']).date()}**\n\n"
        f"_تُعرض الأعداد المطلقة لا النسب المئوية، لأن حجم السجل "
        f"({int(r['incidents'])} حالة) لا يسمح باستخلاص معدلات._"
    )


def _fmt_municipality(df: pd.DataFrame) -> str:
    if df.empty:
        return "لا توجد بيانات."
    top = df.iloc[0]
    lines = [f"🏛️ **توزيع حالات التسمم حسب البلدية**\n"]
    for _, r in df.iterrows():
        lines.append(
            f"- {r['municipality']}: {int(r['incidents'])} حالة، "
            f"{int(r['people_affected'])} مصاب، "
            f"{int(r['convictions'])} إدانة"
        )
    lines.append(
        f"\nالأعلى من حيث عدد المصابين: **{top['municipality']}** "
        f"({int(top['people_affected'])} مصاب)."
    )
    return "\n".join(lines)


def _fmt_trend(df: pd.DataFrame) -> str:
    if df.empty:
        return "لا توجد بيانات."
    lines = ["📈 **التطور الشهري**\n"]
    for _, r in df.iterrows():
        lines.append(f"- {r['month_label']}: {int(r['incidents'])} حالة، "
                     f"{int(r['people_affected'])} مصاب")
    return "\n".join(lines)


def _fmt_repeat(df: pd.DataFrame) -> str:
    if df.empty:
        return ("✅ لا توجد منشأة تكرر بها الحادث خلال الفترة المسجلة "
                "(كل حادثة في منشأة مختلفة).")
    lines = ["⚠️ **منشآت تكرر بها الحادث**\n"]
    for _, r in df.iterrows():
        lines.append(f"- {r['establishment_name']} ({r['municipality']}): "
                     f"{int(r['incidents'])} حوادث، "
                     f"{int(r['people_affected'])} مصاب")
    return "\n".join(lines)


def _fmt_agent(df: pd.DataFrame) -> str:
    if df.empty:
        return "لا توجد بيانات فترة حضانة صالحة."
    lines = ["🔬 **التصنيف الاسترشادي للمسبب حسب فترة الحضانة**\n"]
    for _, r in df.iterrows():
        lines.append(
            f"- {r['agent_class_ar'] or 'غير محدد'}: {int(r['incidents'])} حالة "
            f"(الحضانة {r['min_incubation_h']:g}–{r['max_incubation_h']:g} ساعة)"
        )
    return "\n".join(lines)


def _fmt_audit(df: pd.DataFrame) -> str:
    if df.empty:
        return "لا توجد قرارات مسجلة."
    aligned = int(df["decision_matches_advisory"].sum())
    conv = int((df["decision_en"] == "Convicted").sum())
    lines = [
        f"⚖️ **مراجعة قرارات اللجنة**\n",
        f"- عدد الحالات: {len(df)}",
        f"- قرارات إدانة: {conv} | عدم إدانة: {len(df) - conv}",
        f"- توافق القرار مع القاعدة الاسترشادية: {aligned} من {len(df)}\n",
    ]
    for _, r in df.iterrows():
        lines.append(
            f"- {pd.to_datetime(r['incident_date']).date()} | {r['municipality']} | "
            f"حضانة {r['incubation_hours']:g}س، {int(r['cases_count'])} مصاب "
            f"→ {r['decision_en']} ({r['attribution_reason_ar']})"
        )
    return "\n".join(lines)


def _fmt_establishment(df: pd.DataFrame) -> str:
    if df.empty:
        return "لا توجد حوادث مسجلة لهذه المنشأة."
    lines = [f"🏪 **سجل الحوادث** ({len(df)} حادثة)\n"]
    for _, r in df.iterrows():
        lines.append(f"- {pd.to_datetime(r['incident_date']).date()} | {r['municipality']} | "
                     f"{int(r['cases_count'])} مصاب | {r['decision_ar']}")
    return "\n".join(lines)


def _fmt_quality(df: pd.DataFrame) -> str:
    if df.empty:
        return "✅ لا توجد ملاحظات على جودة البيانات."
    labels = {
        "unparsed_incubation": "فترة حضانة غير قابلة للقراءة",
        "missing_license": "رقم رخصة مفقود",
        "missing_date": "تاريخ مفقود",
        "unknown_decision": "قرار غير معروف",
        "unknown_kinship": "صلة قرابة غير معروفة",
        "not_convicted_without_reason": "عدم إدانة دون تسجيل السبب وفق دليل الوزارة",
    }
    lines = ["🔍 **ملاحظات جودة البيانات**\n"]
    for _, r in df.iterrows():
        lines.append(f"- {labels.get(r['issue'], r['issue'])}: **{int(r['n'])}**")
    return "\n".join(lines)


FORMATTERS = {
    "psn.headline": _fmt_headline,
    "psn.by_municipality": _fmt_municipality,
    "psn.trend": _fmt_trend,
    "psn.repeat_offenders": _fmt_repeat,
    "psn.agent_profile": _fmt_agent,
    "psn.decision_audit": _fmt_audit,
    "psn.establishment_lookup": _fmt_establishment,
    "psn.data_quality": _fmt_quality,
}


# ---------------------------------------------------------------------------
# main entry point
# ---------------------------------------------------------------------------

def handle_poisoning(con, intent_or_name: Any, entities: Any = None,
                     allow_names: bool = True):
    """
    con             : an open DuckDB connection
    intent_or_name  : the Intent enum member, its .name, or a 'psn.*' id
    entities        : your QueryEntities-like object (optional)
    allow_names     : False anonymises establishment names / licence numbers

    Returns (text_ar: str, df: pd.DataFrame | None, meta: dict)
    """
    # accept an enum, an enum name, or a raw intent id
    name = getattr(intent_or_name, "name", intent_or_name)
    intent_id = ENUM_NAME_INTENT.get(name, name)
    if intent_id not in FORMATTERS:
        intent_id = "psn.headline"

    spec = next(s for s in POISONING_INTENTS if s["id"] == intent_id)

    sql = spec["sql"]
    params: list = []
    for key, default in (spec.get("params") or {}).items():
        val = None
        if entities is not None:
            val = getattr(entities, key, None)
        if val is None:
            val = default
        if val is None:
            return ("من فضلك حدد اسم المنشأة أو رقم الرخصة.", None,
                    {"render": "text", "intent": intent_id, "needs_input": key})
        sql = sql.replace("{" + key + "}", "?")
        params.append(val)

    try:
        df = con.execute(sql, params).df() if params else con.execute(sql).df()
    except Exception as exc:
        return (f"تعذر تنفيذ الاستعلام: {exc}", None,
                {"render": "text", "intent": intent_id, "error": True})

    if not allow_names:
        for col in ("establishment_name", "license_no"):
            if col in df.columns:
                df = df.drop(columns=[col])

    text = FORMATTERS[intent_id](df)
    disclaimer = spec.get("disclaimer_ar")
    if disclaimer:
        text += f"\n\n_{disclaimer}_"
    if spec.get("pii") and allow_names:
        text += "\n\n_⚠️ يحتوي على أسماء منشآت — للاستخدام الرسمي المصرح به فقط._"

    return (text, df, {"render": spec.get("render", "table"),
                       "disclaimer": disclaimer,
                       "intent": intent_id,
                       "pii": bool(spec.get("pii"))})