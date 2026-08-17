# -*- coding: utf-8 -*-
"""
inspection_priority_page.py — صفحة Streamlit لأولوية التفتيش
================================================================
جدول Top N + تفكيك المكونات الأربعة عند اختيار صف.
يقرأ فقط من modules.inspection_priority (طبقة القراءة المشتركة) —
مفيش SQL هنا، عشان يفضل نفس المصدر بالظبط زي core_query_engine والصوت.
"""

from typing import TYPE_CHECKING

import pandas as pd
import streamlit as st

from modules.inspection_priority import (
    LEVEL_AR_PLURAL,
    component_breakdown,
    freshness_badge,
    get_low_confidence_alerts,
    get_recommended_route,
    get_top,
    is_available,
    log_inspection,
    undo_inspection,
    get_recent_inspections,
    effective_days_since,
    municipality_trend,
    _muni_label,
)
from modules.inspection_map import show_priority_map

if TYPE_CHECKING:
    from modules.api_service import APIClient


def _get_connection():
    """نفس نمط get_duckdb_connection() في ai_assistant.py — اتصال read-only مشترك."""
    from modules.data_access import get_duckdb_read, _DUCKDB_PATH
    if not _DUCKDB_PATH.exists():
        return None
    return get_duckdb_read()


def _score_color(score: float) -> str:
    """درجة اللون حسب شدة الأولوية — أحمر للحرج، أخضر للمطمئن."""
    if score >= 75:
        return "#dc2626"   # أحمر
    if score >= 50:
        return "#ea580c"   # برتقالي
    if score >= 25:
        return "#d97706"   # كهرماني
    return "#16a34a"       # أخضر


def _route_card_html(label: str, name: str, score: float, subtitle: str = "") -> str:
    color = _score_color(score)
    subtitle_html = (
        f'<div style="font-size:13px;color:#6b7280;margin-top:4px;">{subtitle}</div>'
        if subtitle else ""
    )
    # مهم: كل الـ HTML على سطر واحد بلا مسافات إزاحة — أي سطر يبدأ بـ٤ مسافات
    # أو أكتر جوّه st.markdown بيتفسّر Markdown-code-block مش HTML، فيظهر كنص خام.
    return (
        f'<div style="background:linear-gradient(135deg, {color}15, {color}05);'
        f'border:2px solid {color};border-radius:14px;padding:18px 22px;'
        f'text-align:center;min-width:200px;box-shadow:0 2px 8px rgba(0,0,0,0.06);">'
        f'<div style="font-size:12px;color:{color};font-weight:700;letter-spacing:1px;">{label}</div>'
        f'<div style="font-size:20px;font-weight:800;color:#1f2937;margin-top:4px;">{name}</div>'
        f'<div style="display:inline-block;margin-top:10px;padding:4px 14px;'
        f'background:{color};color:white;border-radius:20px;font-size:15px;font-weight:700;">'
        f'{score:.0f}</div>'
        f'{subtitle_html}'
        f'</div>'
    )


def _arrow_html() -> str:
    return '<div style="text-align:center;font-size:26px;color:#9ca3af;line-height:1;margin:2px 0;">⬇</div>'


def render_route_infographic(route: dict) -> None:
    """التوصية الهرمية كانفوجرافيك: بلدية ← حي ← منشآت، بألوان حسب الدرجة."""
    st.markdown("### 🧭 التوصية الهرمية لليوم")

    if not route.get("found"):
        st.info("لا توجد توصية متاحة حاليًا — البيانات غير كافية لتحديد مسار واضح.")
        return

    m, h, ests = route["municipality"], route["neighborhood"], route["establishments"]

    html_parts = [
        '<div dir="rtl" style="display:flex;flex-direction:column;align-items:center;gap:6px;">',
        _route_card_html("بلدية", _muni_label(m["entity_name"]), m["risk_score"]),
        _arrow_html(),
        _route_card_html("حي", h["entity_name"], h["risk_score"]),
        _arrow_html(),
        '<div style="display:flex;gap:16px;flex-wrap:wrap;justify-content:center;">',
    ]
    for e in ests:
        subtitle = (e.get("reason_ar") or "")[:70]
        html_parts.append(
            _route_card_html("منشأة", e["entity_name"], e["risk_score"], subtitle)
        )
    html_parts.append("</div></div>")

    # "".join بلا أي \n بين الأجزاء — تأكيد إضافي إن الناتج سطر واحد فعليًا
    st.markdown("".join(html_parts), unsafe_allow_html=True)

    # ── تفاصيل الأسباب كاملة تحت الكارت (النص مقصوص فوق للمساحة) ──
    with st.expander("📋 تفاصيل أسباب كل منشأة"):
        for e in ests:
            st.markdown(f"**{e['entity_name']}** — درجة {e['risk_score']:.0f}")
            st.caption(e.get("reason_ar", ""))

    if route.get("warning"):
        warning_html = (
            '<div dir="rtl" style="margin-top:16px;padding:14px 18px;border-radius:10px;'
            'background:#fef3c7;border:1px solid #f59e0b;color:#92400e;font-size:14px;">'
            f"⚠️ {route['warning']}</div>"
        )
        st.markdown(warning_html, unsafe_allow_html=True)


def render_inspection_buttons(route: dict, con) -> None:
    """زر '✅ تم التفتيش' لكل منشأة في التوصية — يسجّل زيارة في inspections_log
    ويعمل rerun فورًا عشان المنشأة تختفي من التوصية ويظهر اللي بعدها.
    قائمة '↩️ آخر الزيارات المسجّلة' بتتقرا من قاعدة البيانات مباشرة، مش من
    session_state — عشان تفضل متاحة حتى لو سجّلت زيارة تانية أو عملت
    reload للصفحة، مش بس آخر ضغطة في نفس الجلسة."""
    if not route.get("found"):
        return
    st.markdown("#### ✅ تسجيل زيارة")
    cols = st.columns(len(route["establishments"]))
    for col, e in zip(cols, route["establishments"]):
        with col:
            if st.button(f"تم تفتيش: {e['entity_name']}", key=f"insp_{e['entity_name']}"):
                log_inspection(
                    entity_name=e["entity_name"],
                    level="establishment",
                    municipality=route["municipality"]["entity_name"],
                    neighborhood=route["neighborhood"]["entity_name"],
                    con=con,
                )
                st.success(f"تم تسجيل زيارة {e['entity_name']} — هتختفي من التوصية "
                          f"لمدة أسبوع، وهتظهر المنشأة اللي بعدها في الترتيب.")
                st.rerun()

    recent = get_recent_inspections(limit=10, level="establishment", con=con)
    if not recent.empty:
        with st.expander(f"↩️ آخر {len(recent)} زيارة مسجّلة — للتراجع", expanded=False):
            for _, r in recent.iterrows():
                rcol1, rcol2 = st.columns([4, 1])
                with rcol1:
                    when = pd.to_datetime(r["inspected_at"]).strftime("%Y-%m-%d %H:%M")
                    st.markdown(f"**{r['entity_name']}** — {r['neighborhood'] or ''} · {when}")
                with rcol2:
                    if st.button("تراجع", key=f"undo_{int(r['id'])}"):
                        undo_inspection(int(r["id"]), con=con)
                        st.success(f"تم التراجع عن تسجيل زيارة {r['entity_name']}.")
                        st.rerun()


def _muni_label_safe(route: dict) -> str:
    return _muni_label(route["municipality"]["entity_name"])


def render_headline(route: dict, alerts_count: int) -> None:
    """سطر العنوان الرئيسي — الحكم أولًا، التفاصيل بعده. أول حاجة يشوفها
    المدير لما يفتح الصفحة، من غير ما يحتاج يقرا جدول."""
    if not route.get("found"):
        return
    n_ests = len(route.get("establishments", []))
    html = (
        '<div dir="rtl" style="border-right:4px solid #dc2626;padding:12px 16px;'
        'background:#fef2f2;border-radius:0 8px 8px 0;margin-bottom:16px;">'
        f'<div style="font-size:16px;font-weight:700;color:#1f2937;">'
        f'{n_ests} منشأة تحتاج زيارة اليوم'
        f'{f" — و{alerts_count} أخرى تحتاج مراجعة يدوية" if alerts_count else ""}'
        f'</div>'
        f'<div style="font-size:13px;color:#6b7280;margin-top:2px;">'
        f'{_muni_label_safe(route)} ← حي {route["neighborhood"]["entity_name"]}'
        f'</div></div>'
    )
    st.markdown(html, unsafe_allow_html=True)


def render_municipality_trend(con) -> None:
    """بلديات نسبة مخالفاتها في ازدياد آخر ٣٠ يوم — مقارنة بفترة قبلها،
    بس للبلديات اللي عندها عدد عينات كافي في الفترتين (٥+)."""
    trend = municipality_trend(window_days=30, con=con)
    if trend.empty:
        return  # مفيش بيانات كافية لمقارنة موثوقة
    worsening = trend[trend["delta_pp"] > 0]
    if worsening.empty:
        return
    with st.expander(f"📈 {len(worsening)} بلدية نسبة مخالفاتها في ازدياد آخر ٣٠ يوم", expanded=False):
        st.caption("مقارنة بآخر ٣٠ يوم قبلها — بلديات فيها عدد عينات كافي في الفترتين بس (٥+).")
        display = worsening.copy()
        display.columns = ["البلدية", "معدل سابق %", "معدل حالي %", "التغيّر (نقطة مئوية)",
                           "عدد عينات سابق", "عدد عينات حالي"]
        st.dataframe(display, use_container_width=True, hide_index=True)


def _confidence_badge(conf: str) -> str:
    return {"high": "🟢 ثقة عالية", "medium": "🟡 ثقة متوسطة", "low": "🔴 ثقة منخفضة"}.get(conf, conf)


def _render_level_table(level: str, con, top_n: int, min_conf: str) -> pd.DataFrame:
    df = get_top(level=level, n=top_n,
                 min_confidence=(None if min_conf == "الكل" else
                                 "high" if min_conf == "عالية فقط" else "medium"),
                 con=con)
    if df.empty:
        st.warning("مفيش نتائج بالفلتر ده — جرّب تقلل حد الثقة.")
        return df

    # آخر معاينة فعلية = الأقرب بين تاريخ آخر عينة معملية وأي زيارة مسجّلة
    # يدويًا — منشأة اتزارت إمبارح ماينفعش تفضل شكلها "مهملة" لحد ما
    # risk_scores يتبني تاني.
    df["effective_days"] = df.apply(
        lambda r: effective_days_since({**r.to_dict(), "level": level}, con=con), axis=1
    )

    display_df = df[["rank_in_level", "entity_name", "risk_score", "confidence",
                     "total_samples", "violations", "effective_days"]].copy()
    display_df.columns = ["الترتيب", "الاسم", "الدرجة", "الثقة", "عدد العينات",
                          "المخالفات", "آخر معاينة (يوم)"]
    display_df["الثقة"] = display_df["الثقة"].map(_confidence_badge)

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "الدرجة": st.column_config.ProgressColumn(
                "الدرجة", min_value=0, max_value=100, format="%.0f"
            ),
        },
    )
    return df


def _render_breakdown(row: dict) -> None:
    """تفكيك المكونات الأربعة — إلزامي حسب التصميم، مش اختياري."""
    st.markdown(f"### 🔍 {row['entity_name']} — درجة {row['risk_score']:.0f}")
    st.markdown(f"**{row['reason_ar']}**")

    breakdown = component_breakdown(row)
    col1, col2 = st.columns([2, 3])

    with col1:
        st.dataframe(breakdown, use_container_width=True, hide_index=True)

    with col2:
        try:
            import plotly.graph_objects as go
            fig = go.Figure(go.Bar(
                x=breakdown["المساهمة في الدرجة"],
                y=breakdown["المكوّن"],
                orientation="h",
                marker=dict(color=breakdown["المساهمة في الدرجة"], colorscale="Reds"),
                text=breakdown["المساهمة في الدرجة"],
                texttemplate="%{text:.1f}",
            ))
            fig.update_layout(height=260, margin=dict(l=10, r=10, t=10, b=10),
                             xaxis_title="المساهمة في الدرجة الكلية")
            st.plotly_chart(fig, use_container_width=True)
        except Exception:
            pass  # الجدول كافي لو plotly مش متاح

    st.caption(
        f"📅 {int(row['total_samples'])} عينة | "
        f"آخر عينة قبل {int(row['days_since_last_sample'])} يوم | "
        f"أساس المنشأة: {row.get('establishment_basis', 'n/a')}"
    )
    if row.get("confidence") == "low":
        st.info("⚠️ عدد عينات قليل لهذا الكيان — الدرجة مؤشر أولي وليست حكمًا نهائيًا.")


def show_inspection_priority_page(api_client: "APIClient | None" = None) -> None:
    """نقطة الدخول — مسجّلة في PAGES dict بتاع app_new.py."""
    st.header("🎯 أولوية التفتيش")
    st.caption("طبقة قرار محسوبة مسبقًا (Bayesian shrinkage + خطورة المنتج + فجوة التغطية + الاتجاه)")

    con = _get_connection()
    if con is None or not is_available(con=con):
        st.error("⚠️ جدول أولوية التفتيش غير مبني بعد.")
        st.code("python scripts/build_risk_scores.py", language="bash")
        return

    # ── التوصية الهرمية + التنبيهات (لازم تتحسب قبل سطر العنوان، عشان
    # العنوان بيلخّص نتيجتهم) ──
    capacity = st.slider(
        "🚗 كام منشأة تقدر فرقة التفتيش تزورها في هذه الرحلة؟",
        min_value=1, max_value=5, value=2,
        help="يحدد عدد المنشآت المعروضة في التوصية داخل الحي المختار.",
    )
    route = get_recommended_route(min_confidence="medium", top_n_establishments=capacity, con=con)
    alerts = get_low_confidence_alerts(top=5, con=con)

    # ── سطر العنوان الرئيسي — أول حاجة يشوفها المدير ──
    render_headline(route, len(alerts))

    st.info(f"ℹ️ {freshness_badge(con=con)}")

    render_route_infographic(route)
    render_inspection_buttons(route, con)

    if not alerts.empty:
        with st.expander(
            f"⚠️ {len(alerts)} منشأة درجتها عالية لكن بعينات قليلة — تحتاج مراجعة يدوية",
            expanded=False,
        ):
            st.caption(
                "مستبعدة من التوصية الأساسية عمدًا (الثقة الإحصائية منخفضة)، "
                "لكن الدرجة العالية تستاهل تنبيه — راجعها بنفسك قبل تجاهلها."
            )
            for _, r in alerts.iterrows():
                st.markdown(f"**{r['entity_name']}** — درجة {r['risk_score']:.0f} "
                           f"({int(r['total_samples'])} عينة فقط)")
                st.caption(r["reason_ar"])

    render_municipality_trend(con)

    st.markdown("---")
    show_priority_map(con, get_top, route=route)

    st.markdown("---")
    st.markdown("### 📊 الترتيب الكامل حسب المستوى")

    # ── إعدادات العرض ──
    col1, col2, col3 = st.columns([2, 2, 2])
    with col1:
        level_ar = st.radio("المستوى", ["منشآت", "أحياء", "بلديات"], horizontal=True)
        level = {"منشآت": "establishment", "أحياء": "neighborhood",
                 "بلديات": "municipality"}[level_ar]
    with col2:
        top_n = st.slider("عدد النتائج", 5, 50, 10, step=5)
    with col3:
        min_conf = st.selectbox("حد الثقة", ["متوسطة فأعلى", "عالية فقط", "الكل"], index=0)

    if min_conf == "الكل":
        st.warning("⚠️ عرض كل الكيانات بما فيها منخفضة الثقة (عدد عينات قليل) — النتائج قد تكون ضجيج.")

    st.markdown(f"### أعلى {top_n} {LEVEL_AR_PLURAL.get(level, 'كيانات')} أولوية")
    df = _render_level_table(level, con, top_n, min_conf)

    if df.empty:
        return

    # ── التفكيك عند اختيار كيان ──
    st.markdown("---")
    st.markdown("### لماذا هذا الترتيب؟")
    choice = st.selectbox(
        "اختر كيانًا لعرض تفكيك درجة الأولوية",
        options=df["entity_id"].tolist(),
        format_func=lambda eid: df.loc[df["entity_id"] == eid, "entity_name"].iloc[0],
    )
    if choice:
        row = df.loc[df["entity_id"] == choice].iloc[0].to_dict()
        _render_breakdown(row)

    # ── تصدير ──
    st.markdown("---")
    import io
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    buf.seek(0)
    st.download_button(
        "📥 تحميل الجدول كامل (Excel)", data=buf,
        file_name=f"inspection_priority_{level}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    