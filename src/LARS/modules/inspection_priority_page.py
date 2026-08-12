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
    get_top,
    is_available,
)

if TYPE_CHECKING:
    from modules.api_service import APIClient


def _get_connection():
    """نفس نمط get_duckdb_connection() في ai_assistant.py — اتصال read-only مشترك."""
    from modules.data_access import get_duckdb_read, _DUCKDB_PATH
    if not _DUCKDB_PATH.exists():
        return None
    return get_duckdb_read()


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

    display_df = df[["rank_in_level", "entity_name", "risk_score", "confidence",
                      "total_samples", "violations", "days_since_last_sample"]].copy()
    display_df.columns = ["الترتيب", "الاسم", "الدرجة", "الثقة", "عدد العينات",
                           "المخالفات", "أيام بدون عينات"]
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

    st.info(f"ℹ️ {freshness_badge(con=con)}")

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