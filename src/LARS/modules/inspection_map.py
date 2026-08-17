# -*- coding: utf-8 -*-
"""
modules/inspection_map.py — خريطة أولوية الأحياء
====================================================
يكمّل الانفوجرافيك الهرمي، مش بديل له: الانفوجرافيك بيشرح "ليه" (سلسلة
الأسباب اللي تخلي التوصية قابلة للدفاع عنها)، والخريطة بتجاوب "إزاي أنفذها
النهاردة فعليًا" (ترتيب الزيارة، التجميع الجغرافي).

قرار تصميم مقصود: مفيش وميض مستمر (blinking). عمرها ما بتدي إحساس بالثقة
في تقرير حكومي، وبتكون مصدر إزعاج بصري وحتى مشكلة accessibility. البديل:
- شدة اللون (heatmap-style) بتوصل الأولوية من أول نظرة من غير أي حركة.
- نبضة واحدة بس (single CSS animation, مش infinite) على أي حي اتغيرت
  أولويته من آخر مرة اتفتحت فيها الصفحة — مش وميض مستمر.
- badge "🆕 محدّث" صريح بدل ما المستخدم يكتشف التغيير بنفسه.
"""

import streamlit as st
import plotly.graph_objects as go

from modules.buraydah_coords import BURAYDAH_NEIGHBORHOODS_COORDS, BURAYDAH_CENTER


def _nearest_neighbor_order(points: list[dict]) -> list[dict]:
    """ترتيب بسيط (nearest-neighbor heuristic) — كافي جدًا لعدد صغير من
    المحطات (٣-٥ في رحلة واحدة)، مش محتاجين حل TSP معقد. البداية = أول
    عنصر في القائمة (المفروض يكون أعلى CRP، جاي مرتب من الكاسكيد بالفعل)."""
    if not points:
        return []
    remaining = points[1:]
    ordered = [points[0]]
    current = points[0]
    while remaining:
        nxt = min(remaining, key=lambda p: (
            (p["lat"] - current["lat"]) ** 2 + (p["lon"] - current["lon"]) ** 2
        ))
        ordered.append(nxt)
        remaining.remove(nxt)
        current = nxt
    return ordered


def build_priority_map(neighborhood_rows, recommended_names=None, previous_top_names=None):
    """
    neighborhood_rows: list of dicts، كل واحد فيه على الأقل entity_name و
        risk_score (من get_top(level='neighborhood', ...) مثلًا).
    recommended_names: أسماء الأحياء اللي في مسار الرحلة المقترحة اليوم —
        دول بس اللي بياخدوا رقم ترتيب زيارة (١، ٢، ٣...) على الخريطة.
    previous_top_names: أسماء أعلى الأحياء من آخر مرة الصفحة اتفتحت فيها
        (محفوظة في st.session_state من المستدعي) — أي اسم جديد النهاردة
        مش كان موجود قبل كده بياخد badge "🆕 محدّث".

    يرجّع (fig, updated_badges: list[str]) — الـ badges بتتعرض تحت
    الخريطة كـ HTML نبضة واحدة، مش جوّه الخريطة نفسها.
    """
    recommended_names = set(recommended_names or [])
    previous_top_names = set(previous_top_names or [])

    points = []
    for row in neighborhood_rows:
        name = row["entity_name"]
        coord = BURAYDAH_NEIGHBORHOODS_COORDS.get(name)
        if coord is None:
            continue  # حي مش موجود في جدول الإحداثيات — يتجاهل بهدوء
        points.append({
            "name": name, "lat": coord["lat"], "lon": coord["lon"],
            "score": row.get("risk_score", 0),
        })

    if not points:
        return None, []

    # كل الأحياء — شدة اللون فقط، بدون ترقيم
    fig = go.Figure(go.Scattermapbox(
        lat=[p["lat"] for p in points],
        lon=[p["lon"] for p in points],
        mode="markers",
        marker=dict(
            size=[14 + p["score"] / 6 for p in points],
            color=[p["score"] for p in points],
            colorscale="Reds",
            cmin=0, cmax=100,
            showscale=True,
            colorbar=dict(title="الدرجة"),
        ),
        text=[f"{p['name']} — {p['score']:.0f}" for p in points],
        hoverinfo="text",
        name="كل الأحياء",
    ))

    # مسار الرحلة المقترحة — أرقام ترتيب فوق العلامات، مرتبة nearest-neighbor
    route_points = [p for p in points if p["name"] in recommended_names]
    if route_points:
        route_points = sorted(route_points, key=lambda p: -p["score"])  # يبدأ بأعلى CRP
        route_points = _nearest_neighbor_order(route_points)
        fig.add_trace(go.Scattermapbox(
            lat=[p["lat"] for p in route_points],
            lon=[p["lon"] for p in route_points],
            mode="lines+markers+text",
            line=dict(width=3, color="#1f2937"),
            marker=dict(size=26, color="#1f2937"),
            text=[str(i) for i in range(1, len(route_points) + 1)],
            textfont=dict(color="white", size=13, family="Arial Black"),
            textposition="middle center",
            hoverinfo="skip",
            name="مسار الزيارة المقترح",
        ))

    fig.update_layout(
        mapbox=dict(
            style="open-street-map",
            center=BURAYDAH_CENTER,
            zoom=11,
        ),
        margin=dict(l=0, r=0, t=0, b=0),
        height=460,
        showlegend=False,
    )

    updated = [p["name"] for p in points if p["name"] not in previous_top_names]
    return fig, updated


def render_update_badges(updated_names: list[str]) -> None:
    """نبضة واحدة (مش وميض مستمر) لأي حي جديد ظهر في أعلى الأولويات —
    animation بدون infinite بتتشغل مرة واحدة كل ما الصفحة تتحدث، مش حركة
    مستمرة مزعجة."""
    if not updated_names:
        return
    css = """
    <style>
    @keyframes pulseOnce {
        0%   { transform: scale(0.9); opacity: 0; }
        50%  { transform: scale(1.05); opacity: 1; }
        100% { transform: scale(1); opacity: 1; }
    }
    .lars-update-badge {
        display: inline-block; animation: pulseOnce 0.6s ease-out;
        background: #fef3c7; border: 1px solid #f59e0b; color: #92400e;
        border-radius: 20px; padding: 4px 12px; margin: 2px 6px 2px 0;
        font-size: 13px; font-weight: 600;
    }
    </style>
    """
    badges = "".join(
        f'<span class="lars-update-badge">🆕 محدّث: {name}</span>'
        for name in updated_names
    )
    st.markdown(css + f'<div dir="rtl">{badges}</div>', unsafe_allow_html=True)


def show_priority_map(con, get_top_fn, route: dict = None) -> None:
    """
    نقطة الدخول — تتنادى من inspection_priority_page.py.
    get_top_fn: مرّر get_top من inspection_priority.py (تجنب import دائري).
    route: ناتج get_recommended_route() لو موجود، عشان نلوّن مسار الرحلة.
    """
    st.markdown("### 🗺️ خريطة الأحياء حسب الأولوية")

    hoods_df = get_top_fn(level="neighborhood", n=200, con=con)
    if hoods_df.empty:
        st.info("لا توجد بيانات كافية لعرض الخريطة.")
        return

    rows = hoods_df.to_dict("records")

    recommended_names = []
    if route and route.get("found"):
        recommended_names = [route["neighborhood"]["entity_name"]]

    previous_top = st.session_state.get("_lars_prev_top_neighborhoods", set())
    current_top = set(hoods_df.head(10)["entity_name"])

    fig, updated = build_priority_map(rows, recommended_names=recommended_names,
                                      previous_top_names=previous_top)
    if fig is None:
        st.info("لا توجد إحداثيات مطابقة للأحياء الحالية — راجع buraydah_coords.py.")
        return

    st.plotly_chart(fig, use_container_width=True)
    render_update_badges(updated)

    # يتحفظ لآخر مرة الصفحة اتفتحت فيها في نفس الجلسة — النبضة تظهر مرة
    # واحدة بس، مش كل rerun داخل نفس الجلسة
    st.session_state["_lars_prev_top_neighborhoods"] = current_top

    st.caption(
        "شدة اللون = الأولوية (أحمر غامق = الأعلى). المسار الأسود المرقّم "
        "= ترتيب الزيارة المقترح لليوم، بأقصر مسافة تقريبية بين المحطات."
    )