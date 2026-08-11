# -*- coding: utf-8 -*-
"""
inspection_priority.py — طبقة القراءة لجدول `risk_scores`
==========================================================
مصدر واحد للحقيقة لكل الواجهات: core_query_engine (نص/صوت) + Streamlit.
لا يحسب أي شيء — الحساب كله في scripts/build_risk_scores.py.

ملاحظة مهمة: كل دالة هنا آمنة لو الجدول مش موجود (deploy من غير build)
— بترجع فاضي مع رسالة واضحة بدل ما تكسر الخدمة.
"""

from pathlib import Path

import duckdb
import pandas as pd

_HERE = Path(__file__).resolve().parent                 # src/LARS/modules
DEFAULT_DB = str(_HERE.parent / "data" / "lars_data.duckdb")
TABLE = "risk_scores"

LEVEL_AR = {
    "establishment": "منشأة",
    "neighborhood": "حي",
    "municipality": "بلدية",
}
LEVEL_AR_PLURAL = {
    "establishment": "منشآت",
    "neighborhood": "أحياء",
    "municipality": "بلديات",
}


def _connect(db_path=None):
    return duckdb.connect(db_path or DEFAULT_DB, read_only=True)


# ---------------------------------------------------------------- availability

def is_available(db_path=None) -> bool:
    """هل الجدول موجود؟ — يتنادى قبل أي عرض في الواجهات."""
    con = None
    try:
        con = _connect(db_path)
        con.execute(f"SELECT 1 FROM {TABLE} LIMIT 1")
        return True
    except Exception:
        return False
    finally:
        if con:
            con.close()


def get_metadata(db_path=None) -> dict:
    """بيانات الحداثة — تتعرض كـ badge فوق أي جدول أولوية."""
    con = None
    try:
        con = _connect(db_path)
        row = con.execute(f"""
            SELECT MAX(computed_at)  AS computed_at,
                   MAX(data_through) AS data_through,
                   MAX(engine_version) AS engine_version,
                   MAX(violation_basis) AS violation_basis,
                   COUNT(*) AS n_rows
            FROM {TABLE}
        """).df().iloc[0].to_dict()
        levels = con.execute(
            f"SELECT level, COUNT(*) AS n FROM {TABLE} GROUP BY 1").df()
        row["levels"] = dict(zip(levels["level"], levels["n"]))
        row["available"] = True
        return row
    except Exception as e:
        return {"available": False, "error": str(e)}
    finally:
        if con:
            con.close()


def freshness_badge(db_path=None) -> str:
    """سطر شفافية جاهز للعرض."""
    m = get_metadata(db_path)
    if not m.get("available"):
        return "⚠️ جدول الأولويات غير مبني — شغّل scripts/build_risk_scores.py"
    dt = pd.to_datetime(m["data_through"]).date()
    ca = pd.to_datetime(m["computed_at"]).strftime("%Y-%m-%d %H:%M")
    return f"محسوب في {ca} — من بيانات حتى {dt} ({m['engine_version']})"


# ---------------------------------------------------------------- queries

def get_top(level: str = "establishment", n: int = 10,
            municipality: str = None, neighborhood: str = None,
            min_confidence: str = None, db_path: str = None) -> pd.DataFrame:
    """
    أعلى n كيان أولوية.
    min_confidence: 'high' | 'medium' → يستبعد الكيانات قليلة العينات.
    """
    con = None
    try:
        con = _connect(db_path)
        where = ["level = ?"]
        params = [level]
        if municipality:
            where.append("parent_municipality = ?")
            params.append(municipality)
        if neighborhood:
            where.append("parent_neighborhood = ?")
            params.append(neighborhood)
        if min_confidence == "high":
            where.append("confidence = 'high'")
        elif min_confidence == "medium":
            where.append("confidence IN ('high','medium')")
        params.append(int(n))
        return con.execute(
            f"SELECT * FROM {TABLE} WHERE {' AND '.join(where)} "
            f"ORDER BY risk_score DESC LIMIT ?", params).df()
    except Exception:
        return pd.DataFrame()
    finally:
        if con:
            con.close()


def get_entity(entity_id: str, level: str = "establishment",
               db_path: str = None) -> dict:
    """صف واحد كامل — لشاشة التفكيك لما المدير يضغط على منشأة."""
    con = None
    try:
        con = _connect(db_path)
        df = con.execute(
            f"SELECT * FROM {TABLE} WHERE level = ? AND entity_id = ?",
            [level, str(entity_id)]).df()
        return {} if df.empty else df.iloc[0].to_dict()
    except Exception:
        return {}
    finally:
        if con:
            con.close()


def search_entity(name: str, level: str = "establishment",
                  db_path: str = None) -> pd.DataFrame:
    """بحث بالاسم — لسؤال 'ما درجة أولوية منشأة كذا؟'"""
    con = None
    try:
        con = _connect(db_path)
        return con.execute(
            f"SELECT * FROM {TABLE} WHERE level = ? AND entity_name ILIKE ? "
            f"ORDER BY risk_score DESC LIMIT 5",
            [level, f"%{name}%"]).df()
    except Exception:
        return pd.DataFrame()
    finally:
        if con:
            con.close()


# ---------------------------------------------------------------- formatting

def to_text(df: pd.DataFrame, level: str = "establishment",
            db_path: str = None) -> str:
    """نص عربي كامل — لردود المحرك النصية (Streamlit chat)."""
    if df.empty:
        return ("لا توجد بيانات أولوية متاحة. "
                "قد يكون جدول التقييم غير مبني بعد.")
    label = LEVEL_AR_PLURAL.get(level, "كيانات")
    lines = [f"**أعلى {len(df)} {label} من حيث أولوية التفتيش:**", ""]
    for _, r in df.iterrows():
        lines.append(f"{int(r['rank_in_level'])}. **{r['entity_name']}** — "
                     f"درجة {r['risk_score']:.0f}")
        lines.append(f"   {r['reason_ar']}")
    lines.append("")
    lines.append(f"_{freshness_badge(db_path)}_")
    return "\n".join(lines)


def to_voice_summary(df: pd.DataFrame, level: str = "establishment",
                     top: int = 3) -> str:
    """
    جملة أو اتنين للصوت — مش الجدول كامل.
    نفس مبدأ voice_summary في lars_service.py.
    """
    if df.empty:
        return "لا توجد بيانات أولوية تفتيش متاحة حاليا."
    d = df.head(top)
    label = LEVEL_AR_PLURAL.get(level, "كيانات")
    names = "، و".join(str(x) for x in d["entity_name"].tolist())

    # السبب الغالب عبر أعلى 3 — مش سبب كل واحد على حدة
    means = {
        "فجوة تفتيش طويلة": float(d["c_coverage"].mean()),
        "سجل مخالفات مرتفع": float(d["c_hist"].mean()),
        "منتجات عالية الخطورة": float(d["c_commodity"].mean()),
    }
    drivers = [k for k, v in sorted(means.items(), key=lambda x: -x[1])[:2] if v > 0.4]
    why = " و".join(drivers) if drivers else "مجموع المؤشرات"
    return (f"أعلى {len(d)} {label} أولوية للتفتيش هي {names}، بسبب {why}.")


def component_breakdown(row: dict) -> pd.DataFrame:
    """تفكيك المكونات الأربعة لصف واحد — للعرض كجدول/بار في Streamlit."""
    comps = [
        ("السجل التاريخي", row.get("c_hist", 0), row.get("w_hist", 0)),
        ("خطورة المنتجات", row.get("c_commodity", 0), row.get("w_commodity", 0)),
        ("فجوة التغطية", row.get("c_coverage", 0), row.get("w_coverage", 0)),
        ("الاتجاه العام", row.get("c_trend", 0), row.get("w_trend", 0)),
    ]
    out = pd.DataFrame(comps, columns=["المكوّن", "القيمة (0-1)", "الوزن"])
    out["المساهمة في الدرجة"] = (out["القيمة (0-1)"] * out["الوزن"] * 100).round(1)
    out["القيمة (0-1)"] = out["القيمة (0-1)"].round(2)
    return out.sort_values("المساهمة في الدرجة", ascending=False)