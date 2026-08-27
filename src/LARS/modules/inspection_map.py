# -*- coding: utf-8 -*-
"""
modules/inspection_map.py — خريطة أولوية الأحياء
====================================================
يكمّل الانفوجرافيك الهرمي، مش بديل له: الانفوجرافيك بيشرح "ليه"، والخريطة
بتجاوب "إزاي أنفذها النهاردة فعليًا" (ترتيب الزيارة، التجميع الجغرافي).

⚠️ ملاحظة مهمة عن الأشكال:
كل حي بيظهر كمضلّع (شكل حقيقي) بدل نقطة دائرية، بس الأشكال دي مبنية على
Voronoi tessellation حول نقطة مركز كل حي (من buraydah_coords.py) — مش
حدود إدارية رسمية. الخط الفاصل بين حيين هو "أقرب نقطة" رياضيًا، مش الحد
المعتمد من البلدية. تقريب بصري كويس للعرض والتخطيط، لكن مايتاخدش كمرجع
قانوني/مساحي. لو عايز حدود رسمية دقيقة لاحقًا: محتاج طبقة GeoJSON من
بلدية بريدة أو OpenStreetMap (boundary=administrative)، وتستبدل بيها
دالة _neighborhood_geojson() هنا فقط — باقي الكود (الألوان، الـ labels،
مسار الرحلة) هيفضل شغال زي ما هو، مصدر الشكل بس هيتغيّر.

قرار تصميم مقصود: مفيش وميض مستمر. البديل: شدة اللون (Choroplethmapbox)
للأولوية، ونبضة واحدة بس (مش infinite) لأي حي جديد في التوب.

الاعتماد الجديد: scipy (لحساب Voronoi) — لازم يتضاف لـ requirements.txt.
"""

import numpy as np
import streamlit as st
import plotly.graph_objects as go
from scipy.spatial import Voronoi

from modules.buraydah_coords import BURAYDAH_NEIGHBORHOODS_COORDS, BURAYDAH_CENTER

# توافق نُسخ Plotly: 6+ غيّر أسماء الأنواع من "Mapbox" لـ "Map" (بيستخدم
# MapLibre بدل Mapbox، مبقاش محتاج token) — بنكتشف الموجود فعليًا بدل ما
# نفترض نسخة معينة، عشان الكود يشتغل على أي بيئة.
if hasattr(go, "Choroplethmapbox"):
    _ChoroplethTrace = go.Choroplethmapbox
    _ScatterTrace = go.Scattermapbox
    _MAP_LAYOUT_KEY = "mapbox"
else:
    _ChoroplethTrace = go.Choroplethmap
    _ScatterTrace = go.Scattermap
    _MAP_LAYOUT_KEY = "map"


def _nearest_neighbor_order(points):
    """ترتيب بسيط (nearest-neighbor heuristic) — كافي لعدد صغير من المحطات (٣-٥)."""
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


def _sutherland_hodgman_clip(subject, clip_poly):
    """يقص مضلّع subject على أي مضلّع محدّب clip_poly (CCW) — مش لازم يبقى
    مستطيل. عمّمناها من نسخة الـ bbox القديمة عشان نقدر نقص على شكل الـ
    convex hull بدل مستطيل، فيبقى الحد الخارجي طبيعي على شكل المدينة
    الفعلي مش مربّع صناعي واضح."""
    def is_left(p, a, b):
        return (b[0]-a[0])*(p[1]-a[1]) - (b[1]-a[1])*(p[0]-a[0]) >= 0

    def intersect(p1, p2, a, b):
        x1, y1 = p1; x2, y2 = p2; x3, y3 = a; x4, y4 = b
        denom = (x1-x2)*(y3-y4) - (y1-y2)*(x3-x4)
        if denom == 0:
            return p2
        t = ((x1-x3)*(y3-y4) - (y1-y3)*(x3-x4)) / denom
        return (x1 + t*(x2-x1), y1 + t*(y2-y1))

    output = list(subject)
    n = len(clip_poly)
    for i in range(n):
        a, b = clip_poly[i], clip_poly[(i+1) % n]
        input_list = output
        output = []
        if not input_list:
            break
        prev = input_list[-1]
        prev_in = is_left(prev, a, b)
        for cur in input_list:
            cur_in = is_left(cur, a, b)
            if cur_in:
                if not prev_in:
                    output.append(intersect(prev, cur, a, b))
                output.append(cur)
            elif prev_in:
                output.append(intersect(prev, cur, a, b))
            prev, prev_in = cur, cur_in
    return output


def _buffered_convex_hull(points, buffer_factor=1.18):
    """Convex hull حوالين كل نقاط الأحياء، ممدّد للخارج شوية (buffer_factor)
    من مركز الكتلة — عشان الأحياء الطرفية ياخدوا مساحة معقولة بدل ما
    يتقصوا لصق حدود الـ hull بالظبط. المهم إن الشكل ده عضوي (بيتبع توزيع
    النقاط الفعلي) مش مستطيل صناعي واضح للعين."""
    from scipy.spatial import ConvexHull
    hull = ConvexHull(points)
    hull_pts = points[hull.vertices]
    center = points.mean(axis=0)
    buffered = center + (hull_pts - center) * buffer_factor
    return [tuple(p) for p in buffered]


def _voronoi_finite_polygons_2d(vor, radius=None):
    """يحوّل مناطق Voronoi اللانهائية (عند الأطراف) لمناطق محدودة، بتمديد
    الأضلاع المفتوحة لمسافة radius قبل القص. Standard recipe."""
    if vor.points.shape[1] != 2:
        raise ValueError("Requires 2D input")
    new_regions = []
    new_vertices = vor.vertices.tolist()
    center = vor.points.mean(axis=0)
    if radius is None:
        radius = (vor.points.max(axis=0) - vor.points.min(axis=0)).max() * 10

    all_ridges = {}
    for (p1, p2), (v1, v2) in zip(vor.ridge_points, vor.ridge_vertices):
        all_ridges.setdefault(p1, []).append((p2, v1, v2))
        all_ridges.setdefault(p2, []).append((p1, v1, v2))

    for p1, region_idx in enumerate(vor.point_region):
        vertices = vor.regions[region_idx]
        if all(v >= 0 for v in vertices):
            new_regions.append(vertices)
            continue
        ridges = all_ridges[p1]
        new_region = [v for v in vertices if v >= 0]
        for p2, v1, v2 in ridges:
            if v2 < 0:
                v1, v2 = v2, v1
            if v1 >= 0:
                continue
            t = vor.points[p2] - vor.points[p1]
            t = t / np.linalg.norm(t)
            n = np.array([-t[1], t[0]])
            midpoint = vor.points[[p1, p2]].mean(axis=0)
            direction = np.sign(np.dot(midpoint - center, n)) * n
            far_point = vor.vertices[v2] + direction * radius
            new_region.append(len(new_vertices))
            new_vertices.append(far_point.tolist())
        vs = np.asarray([new_vertices[v] for v in new_region])
        c = vs.mean(axis=0)
        angles = np.arctan2(vs[:, 1] - c[1], vs[:, 0] - c[0])
        new_region = np.array(new_region)[np.argsort(angles)]
        new_regions.append(new_region.tolist())
    return new_regions, np.asarray(new_vertices)


def _neighborhood_geojson(names):
    """يبني GeoJSON FeatureCollection — مضلّع Voronoi واحد لكل حي.
    ده المكان اللي تستبدله لو جالك طبقة حدود رسمية بعدين."""
    points = np.array([[BURAYDAH_NEIGHBORHOODS_COORDS[n]["lon"],
                        BURAYDAH_NEIGHBORHOODS_COORDS[n]["lat"]] for n in names])
    vor = Voronoi(points)
    regions, vertices = _voronoi_finite_polygons_2d(vor)

    clip_poly = _buffered_convex_hull(points)

    features = []
    for name, region in zip(names, regions):
        poly = [tuple(p) for p in vertices[region]]
        clipped = _sutherland_hodgman_clip(poly, clip_poly)
        if len(clipped) < 3:
            x, y = BURAYDAH_NEIGHBORHOODS_COORDS[name]["lon"], BURAYDAH_NEIGHBORHOODS_COORDS[name]["lat"]
            clipped = [(x-0.005, y-0.005), (x+0.005, y-0.005), (x+0.005, y+0.005), (x-0.005, y+0.005)]
        ring = clipped + [clipped[0]]
        features.append({
            "type": "Feature",
            "id": name,
            "properties": {"name": name},
            "geometry": {"type": "Polygon", "coordinates": [[list(p) for p in ring]]},
        })
    return {"type": "FeatureCollection", "features": features}


def build_priority_choropleth(neighborhood_rows, recommended_names=None, previous_top_names=None):
    """
    neighborhood_rows: list of dicts فيها entity_name و risk_score.
    recommended_names: أسماء الأحياء في مسار الرحلة المقترحة اليوم.
    previous_top_names: أسماء أعلى الأحياء من آخر مرة الصفحة اتفتحت.
    يرجّع (fig, updated_badges).
    """
    recommended_names = set(recommended_names or [])
    previous_top_names = set(previous_top_names or [])

    rows_by_name = {r["entity_name"]: r for r in neighborhood_rows
                    if r["entity_name"] in BURAYDAH_NEIGHBORHOODS_COORDS}
    names = list(rows_by_name.keys())
    if len(names) < 4:
        return None, []  # Voronoi محتاج ٤ نقاط على الأقل

    geojson = _neighborhood_geojson(names)
    scores = [rows_by_name[n].get("risk_score", 0) for n in names]

    fig = go.Figure(_ChoroplethTrace(
        geojson=geojson,
        locations=names,
        z=scores,
        colorscale="Reds",
        zmin=0, zmax=100,
        marker_opacity=0.75,
        marker_line_width=1.5,
        marker_line_color="#ffffff",
        colorbar=dict(title="الدرجة"),
        hovertext=[f"{n} — {s:.0f}" for n, s in zip(names, scores)],
        hoverinfo="text",
    ))

    fig.add_trace(_ScatterTrace(
        lat=[BURAYDAH_NEIGHBORHOODS_COORDS[n]["lat"] for n in names],
        lon=[BURAYDAH_NEIGHBORHOODS_COORDS[n]["lon"] for n in names],
        mode="text",
        text=names,
        textfont=dict(size=11, color="#1f2937", family="Arial Black"),
        hoverinfo="skip",
        showlegend=False,
    ))

    route_points = [{"name": n, "lat": BURAYDAH_NEIGHBORHOODS_COORDS[n]["lat"],
                     "lon": BURAYDAH_NEIGHBORHOODS_COORDS[n]["lon"]}
                    for n in names if n in recommended_names]
    if route_points:
        route_points = sorted(route_points,
                              key=lambda p: -rows_by_name[p["name"]].get("risk_score", 0))
        route_points = _nearest_neighbor_order(route_points)
        fig.add_trace(_ScatterTrace(
            lat=[p["lat"] for p in route_points],
            lon=[p["lon"] for p in route_points],
            mode="lines+markers+text",
            line=dict(width=3, color="#111827"),
            marker=dict(size=26, color="#111827"),
            text=[str(i) for i in range(1, len(route_points) + 1)],
            textfont=dict(color="white", size=13, family="Arial Black"),
            textposition="middle center",
            hoverinfo="skip",
            showlegend=False,
        ))

    fig.update_layout(
        **{_MAP_LAYOUT_KEY: dict(style="open-street-map", center=BURAYDAH_CENTER, zoom=11)},
        margin=dict(l=0, r=0, t=0, b=0),
        height=520,
        showlegend=False,
    )

    updated = [n for n in names if n not in previous_top_names]
    return fig, updated


def render_update_badges(updated_names):
    """نبضة واحدة (مش وميض مستمر) لأي حي جديد ظهر في أعلى الأولويات."""
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


def show_priority_map(con, get_top_fn, route=None):
    """نقطة الدخول — تتنادى من inspection_priority_page.py."""
    st.markdown("### 🗺️ خريطة الأحياء حسب الأولوية")
    st.caption(
        "شكل كل حي تقريب هندسي (Voronoi) حوالين نقطة مركزه — مش حدود إدارية "
        "رسمية. للعرض والتخطيط، مش للاستخدام كمرجع مساحي."
    )

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

    try:
        fig, updated = build_priority_choropleth(
            rows, recommended_names=recommended_names, previous_top_names=previous_top
        )
    except Exception as e:
        st.warning(f"تعذّر بناء خريطة الأشكال ({e}) — راجع أن scipy مثبّت.")
        return

    if fig is None:
        st.info("عدد الأحياء المتاحة قليل جدًا لرسم خريطة أشكال (محتاج ٤ على الأقل).")
        return

    st.plotly_chart(fig, use_container_width=True)
    render_update_badges(updated)

    st.session_state["_lars_prev_top_neighborhoods"] = current_top

    st.caption(
        "شدة اللون = الأولوية (أحمر غامق = الأعلى). المسار الأسود المرقّم "
        "= ترتيب الزيارة المقترح لليوم."
    )