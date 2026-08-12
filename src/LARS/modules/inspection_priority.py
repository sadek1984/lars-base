# -*- coding: utf-8 -*-
"""
inspection_priority.py — طبقة القراءة لجدول `risk_scores`
==========================================================
مصدر واحد للحقيقة لكل الواجهات: core_query_engine (نص/صوت) + Streamlit.
لا يحسب أي شيء — الحساب كله في scripts/build_risk_scores.py.

ملاحظة مهمة: كل دالة هنا آمنة لو الجدول مش موجود (deploy من غير build)
— بترجع فاضي مع رسالة واضحة بدل ما تكسر الخدمة.
"""

import re
from pathlib import Path

import duckdb
import pandas as pd

_HERE = Path(__file__).resolve().parent                 # src/LARS/modules
DEFAULT_DB = str(_HERE.parent / "data" / "lars_data.duckdb")
TABLE = "risk_scores"

_AR_NORM = str.maketrans({
    "أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ـ": "",
    # أرقام عربية-هندية → ASCII، عشان _TOP_N_PATTERN يلقطها
    "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
    "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
})


def norm_ar(s):
    """تطبيع عربي خفيف — نفس منطق build_risk_scores.norm_ar، منسوخ محليًا
    عشان الموديول ده يفضل مستقل من غير استيراد سكريبت البناء."""
    if s is None:
        return None
    s = str(s).translate(_AR_NORM).strip()
    return re.sub(r"\s+", " ", s) or None


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


# ============================================================================
# CLASSIFICATION — نفس نمط عزل التسمم (classify_poisoning) بالظبط
# ============================================================================
# intent_router.py بينادي classify_inspection_priority() قبل أي منطق تاني،
# زي ما بينادي classify_poisoning(). لو رجّعت قيمة، الـ router يرجّع فورًا
# من غير ما يمرّ على قواعد الكشف العادية.

# اسم الـ Intent الداخلي → اسمه في intent_router.Intent enum
PRIORITY_INTENT_ENUM_NAME = {
    "top": "INSPECTION_PRIORITY_TOP",
    "urgent_neighborhood": "INSPECTION_PRIORITY_URGENT_NEIGHBORHOOD",
    "reason": "INSPECTION_PRIORITY_REASON",
    "route": "INSPECTION_PRIORITY_ROUTE",
}

_ROUTE_KEYWORDS = frozenset([
    "التوصية", "خطة الزيارة", "خطة زيارة", "أين نذهب", "اين نذهب",
    "وين نروح", "المسار الموصى", "خطة تفتيش", "أين يجب أن نذهب",
])

_PRIORITY_KEYWORDS = frozenset([
    "أولوية", "اولوية", "أولويات", "اولويات",
    "تفتيش عاجل", "زيارة عاجلة", "حملة رقابية", "تحتاج تفتيش",
    "priority", "inspection priority",
])
_URGENT_KEYWORDS = frozenset([
    "عاجل", "عاجلة", "urgent",
])
_REASON_KEYWORDS = frozenset([
    "ليه", "لماذا", "السبب", "ما سبب", "ليش", "why",
])
_TOP_N_PATTERN = re.compile(r"(?:اعلي|افضل|top)\s*(\d+)")  # النص بيتفحص بعد norm_ar (ى→ي)


def classify_inspection_priority(query: str):
    """
    كشف مبكر ومعزول لأسئلة أولوية التفتيش — قبل أي قاعدة تانية في الراوتر.
    يرجّع None لو السؤال مش عن أولوية التفتيش (يسيب الراوتر يكمل عادي).
    """
    q = norm_ar(query) or ""

    # التوصية الهرمية مالهاش كلمة "أولوية" بالضرورة (زي "خطة الزيارة")،
    # فبتتفحص قبل شرط has_priority مباشرة.
    if any(k in q for k in _ROUTE_KEYWORDS):
        return "route"

    has_priority = any(k in q for k in _PRIORITY_KEYWORDS)
    if not has_priority:
        return None

    is_neighborhood = any(w in q for w in ("حي", "أحياء", "احياء", "الحى"))
    is_urgent = any(k in q for k in _URGENT_KEYWORDS)
    is_reason = any(k in q for k in _REASON_KEYWORDS)

    if is_reason:
        return "reason"
    if is_neighborhood and is_urgent:
        return "urgent_neighborhood"
    return "top"


_REASON_STRIP_WORDS = (
    "لماذا", "ليه", "ليش", "why", "السبب", "ما سبب", "سبب",
    "أولوية", "اولوية", "؟", "?",
)


def extract_entity_name_for_reason(query: str) -> str:
    """
    يشيل كلمات السؤال المعروفة (لماذا/السبب/أولوية...) من الجملة عشان يفضل
    بس اسم الكيان — search_entity() بتعمل ILIKE '%name%' فمحتاجة اسم نضيف،
    مش الجملة كاملة (وإلا هترجع فاضية دايمًا).
    """
    q = query
    for w in _REASON_STRIP_WORDS:
        q = q.replace(w, " ")
    return re.sub(r"\s+", " ", q).strip()


def extract_priority_params(query: str) -> dict:
    """
    يستخرج مستوى الكيان وعدد الـ N من السؤال — يتنادى في الـ handler
    (مش في الكشف نفسه، عشان نفس فصل entity-extraction عن intent في الراوتر).
    """
    q = norm_ar(query) or ""
    level = ("neighborhood" if any(w in q for w in ("حي", "أحياء", "احياء", "الحى"))
             else "municipality" if any(w in q for w in ("بلدية", "بلديات"))
             else "establishment")
    m = _TOP_N_PATTERN.search(q)
    top_n = int(m.group(1)) if m else 10
    return {"level": level, "top_n": min(top_n, 50)}


def _connect(db_path=None):
    return duckdb.connect(db_path or DEFAULT_DB, read_only=True)


def _resolve(con, db_path):
    """
    يرجّع (connection, should_close).
    لو con اتبعت (من core_query_engine._get_connection() مثلًا) بنستخدمها
    زي ما هي من غير قفل — المستدعي مسؤول عنها. غير كده بنفتح اتصال جديد
    ونقفله إحنا، عشان الاستخدام المستقل (سكريبتات/اختبارات) يفضل شغال.
    """
    if con is not None:
        return con, False
    return _connect(db_path), True


# ---------------------------------------------------------------- availability

def is_available(db_path=None, con=None) -> bool:
    """هل الجدول موجود؟ — يتنادى قبل أي عرض في الواجهات."""
    c, should_close = None, False
    try:
        c, should_close = _resolve(con, db_path)
        c.execute(f"SELECT 1 FROM {TABLE} LIMIT 1")
        return True
    except Exception:
        return False
    finally:
        if should_close and c:
            c.close()


def get_metadata(db_path=None, con=None) -> dict:
    """بيانات الحداثة — تتعرض كـ badge فوق أي جدول أولوية."""
    c, should_close = None, False
    try:
        c, should_close = _resolve(con, db_path)
        row = c.execute(f"""
            SELECT MAX(computed_at)  AS computed_at,
                   MAX(data_through) AS data_through,
                   MAX(engine_version) AS engine_version,
                   MAX(violation_basis) AS violation_basis,
                   COUNT(*) AS n_rows
            FROM {TABLE}
        """).df().iloc[0].to_dict()
        levels = c.execute(
            f"SELECT level, COUNT(*) AS n FROM {TABLE} GROUP BY 1").df()
        row["levels"] = dict(zip(levels["level"], levels["n"]))
        row["available"] = True
        return row
    except Exception as e:
        return {"available": False, "error": str(e)}
    finally:
        if should_close and c:
            c.close()


def freshness_badge(db_path=None, con=None) -> str:
    """سطر شفافية جاهز للعرض."""
    m = get_metadata(db_path, con=con)
    if not m.get("available"):
        return "⚠️ جدول الأولويات غير مبني — شغّل scripts/build_risk_scores.py"
    dt = pd.to_datetime(m["data_through"]).date()
    ca = pd.to_datetime(m["computed_at"]).strftime("%Y-%m-%d %H:%M")
    return f"محسوب في {ca} — من بيانات حتى {dt} ({m['engine_version']})"


# ---------------------------------------------------------------- queries

OVERRIDES_TABLE = "risk_overrides"


def _apply_overrides(df: pd.DataFrame, level: str, con) -> pd.DataFrame:
    """
    يطبّق أي رفع أولوية يدوي (manual_boost) موجود في جدول risk_overrides —
    جدول منفصل بيتكتب فيه مباشرة عن طريق set_manual_override.py، ومش بيتمسح
    مع كل إعادة بناء لـ risk_scores (عكس لو كان عمود جوّه الجدول نفسه).

    شفافية: أي صف اترفع بتتضاف له علامة override=True وسبب مضاف لـ reason_ar،
    عشان محدش يشوف رقم اتغيّر من غير ما يعرف ليه (نفس مبدأ التصميم الأساسي).
    """
    if df.empty:
        return df
    try:
        active = con.execute(
            f"SELECT entity_id, boost, note FROM {OVERRIDES_TABLE} "
            f"WHERE level = ? AND (expires_at IS NULL OR expires_at > now())",
            [level]
        ).df()
    except Exception:
        return df  # الجدول مش موجود — طبيعي لو مفيش overrides اتحطت أبدًا

    if active.empty:
        return df

    df = df.merge(active, on="entity_id", how="left")
    df["boost"] = df["boost"].fillna(0.0)
    df["original_score"] = df["risk_score"]
    df["manual_override"] = df["boost"] != 0.0
    df["risk_score"] = (df["risk_score"] + df["boost"]).clip(0, 100)

    def _amend_reason(row):
        if not row["manual_override"]:
            return row["reason_ar"]
        note = f" — 🔧 رفع يدوي (+{row['boost']:.0f}"
        if pd.notna(row.get("note")):
            note += f": {row['note']}"
        note += ")"
        return str(row["reason_ar"]) + note

    df["reason_ar"] = df.apply(_amend_reason, axis=1)
    df = df.drop(columns=["boost", "note"], errors="ignore")
    df = df.sort_values("risk_score", ascending=False).reset_index(drop=True)
    df["rank_in_level"] = range(1, len(df) + 1)
    return df


def get_top(level: str = "establishment", n: int = 10,
            municipality: str = None, neighborhood: str = None,
            min_confidence: str = None, db_path: str = None,
            con=None, apply_overrides: bool = True) -> pd.DataFrame:
    """
    أعلى n كيان أولوية.
    min_confidence: 'high' | 'medium' → يستبعد الكيانات قليلة العينات.
    apply_overrides: يطبّق risk_overrides لو موجودة (افتراضي مفعّل — عشان
                     كل الواجهات "مصدر واحد للحقيقة" وتحترم الرفع اليدوي أوتوماتيك).
    """
    c, should_close = None, False
    try:
        c, should_close = _resolve(con, db_path)
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

        # نجيب أعلى fetch_n بالترتيب الأصلي، وبرضه نجيب أي صف عليه override
        # صراحة (بغض النظر عن ترتيبه الأصلي) — وإلا منشأة متأخرة جدًا برفع
        # كبير مستحيل توصلها الأصل، لأنها هتبقى خارج fetch_n من الأول.
        fetch_n = int(n) * 3 if apply_overrides else int(n)
        base_params = list(params) + [fetch_n]
        df = c.execute(
            f"SELECT * FROM {TABLE} WHERE {' AND '.join(where)} "
            f"ORDER BY risk_score DESC LIMIT ?", base_params).df()

        if apply_overrides:
            try:
                override_ids = c.execute(
                    f"SELECT DISTINCT entity_id FROM {OVERRIDES_TABLE} "
                    f"WHERE level = ? AND (expires_at IS NULL OR expires_at > now())",
                    [level]
                ).df()["entity_id"].tolist()
            except Exception:
                override_ids = []

            missing_ids = [i for i in override_ids if i not in df["entity_id"].values]
            if missing_ids:
                placeholders = ",".join(["?"] * len(missing_ids))
                extra = c.execute(
                    f"SELECT * FROM {TABLE} WHERE {' AND '.join(where)} "
                    f"AND entity_id IN ({placeholders})",
                    list(params) + missing_ids
                ).df()
                if not extra.empty:
                    df = pd.concat([df, extra], ignore_index=True)

            df = _apply_overrides(df, level, c)

        return df.head(int(n)).reset_index(drop=True)
    except Exception:
        return pd.DataFrame()
    finally:
        if should_close and c:
            c.close()


def get_entity(entity_id: str, level: str = "establishment",
               db_path: str = None, con=None) -> dict:
    """صف واحد كامل — لشاشة التفكيك لما المدير يضغط على منشأة."""
    c, should_close = None, False
    try:
        c, should_close = _resolve(con, db_path)
        df = c.execute(
            f"SELECT * FROM {TABLE} WHERE level = ? AND entity_id = ?",
            [level, str(entity_id)]).df()
        return {} if df.empty else df.iloc[0].to_dict()
    except Exception:
        return {}
    finally:
        if should_close and c:
            c.close()


def search_entity(name: str, level: str = "establishment",
                  db_path: str = None, con=None) -> pd.DataFrame:
    """بحث بالاسم — لسؤال 'ما درجة أولوية منشأة كذا؟'"""
    c, should_close = None, False
    try:
        c, should_close = _resolve(con, db_path)
        return c.execute(
            f"SELECT * FROM {TABLE} WHERE level = ? AND entity_name ILIKE ? "
            f"ORDER BY risk_score DESC LIMIT 5",
            [level, f"%{name}%"]).df()
    except Exception:
        return pd.DataFrame()
    finally:
        if should_close and c:
            c.close()


# ---------------------------------------------------------------- formatting

def to_text(df: pd.DataFrame, level: str = "establishment",
            db_path: str = None, con=None) -> str:
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
    lines.append(f"_{freshness_badge(db_path, con=con)}_")
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


# ============================================================================
# التوصية الهرمية — بلدية ← حي ← منشآت (CRP-based)
# ============================================================================
# اتجاه Top-Down، لكن الاختيار مش بمتوسط درجة البلدية/الحي (بيميل يخبي حي
# كارثي جوّا بلدية متوسطة). بدل كده بنحسب "Concentrated Risk Potential":
#   CRP = مجموع (درجة المنشأة - threshold) لكل منشأة درجتها فوق الـ threshold
# threshold = متوسط + انحراف معياري لدرجات المنشآت المؤهلة (medium/high).
# ده بيدّي وزن حقيقي للـ clusters (٣ منشآت بدرجة ٨٥ أهم من منشأة واحدة ٩٩)
# من غير ما نخفي outlier وحيد.
#
# فلتر إضافي: البلدية/الحي نفسه لازم يكون confidence != 'low' (مش بس
# المنشآت) — كيان بعينتين بس معندوش ثقة كافية يتاخد كأساس لتوصية.
#
# صمّام أمان: بعد اختيار الحي، بنقارنه بأعلى CRP حي **على مستوى النظام كله**
# (مش بس جوّا البلدية المختارة) — لو فيه حي بـCRP أعلى في بلدية تانية، بيتضاف
# كتحذير صريح. ده بيمسك clusters كاملة، مش نقطة واحدة بس زي التصميم القديم.

def _crp_threshold(establishment_df: pd.DataFrame) -> float:
    if establishment_df.empty:
        return 100.0  # لا شيء يتجاوزه — يمنع القسمة على صفر لاحقًا
    return float(establishment_df["risk_score"].mean() + establishment_df["risk_score"].std(ddof=0))


def get_recommended_route(min_confidence: str = "medium", top_n_establishments: int = 2,
                          db_path: str = None, con=None) -> dict:
    """
    يرجّع dict:
      {"found": bool, "municipality": dict, "neighborhood": dict,
       "establishments": [dict, ...], "warning": str|None, "threshold": float}
    """
    c, should_close = _resolve(con, db_path)
    try:
        est_df = get_top(level="establishment", n=100000, min_confidence=min_confidence, con=c)
        if est_df.empty:
            return {"found": False}

        threshold = _crp_threshold(est_df)
        est_df = est_df.copy()
        est_df["excess"] = (est_df["risk_score"] - threshold).clip(lower=0)

        # ثقة التجميع نفسه — أي بلدية/حي بثقة منخفضة (عدد عينات إجمالي قليل)
        # مايتاخدش كأساس توصية، حتى لو CRP بتاعه عالي بالصدفة
        muni_all = get_top(level="municipality", n=100000, con=c, apply_overrides=False)
        hood_all = get_top(level="neighborhood", n=100000, con=c, apply_overrides=False)
        muni_conf_ok = set(muni_all.loc[muni_all["confidence"] != "low", "entity_name"])
        hood_conf_ok = set(hood_all.loc[hood_all["confidence"] != "low", "entity_name"])

        crp_muni = (est_df.groupby("parent_municipality")["excess"].sum()
                    .sort_values(ascending=False))
        # CRP على مستوى الحي — محسوبة مرة على كل البيانات، تتستخدم مرتين:
        # مرة مفلترة لكل بلدية أثناء الـ cascade، ومرة عالميًا لصمّام الأمان
        crp_hood_global = (est_df.groupby(["parent_neighborhood", "parent_municipality"])["excess"]
                           .sum().reset_index().sort_values("excess", ascending=False))
        crp_hood_global = crp_hood_global[
            crp_hood_global["parent_neighborhood"].isin(hood_conf_ok)
        ]

        chosen_muni_name = chosen_hood_name = None

        for muni_name, muni_crp in crp_muni.items():
            if muni_crp <= 0 or muni_name not in muni_conf_ok:
                continue
            local = crp_hood_global[crp_hood_global["parent_municipality"] == muni_name]
            local = local[local["excess"] > 0]
            if local.empty:
                continue  # البلدية دي CRP بتاعها موجب بس مفيش حي فردي مؤهل فيها (نادر)
            chosen_muni_name = muni_name
            chosen_hood_name = local.iloc[0]["parent_neighborhood"]
            break

        if chosen_muni_name is None:
            return {"found": False, "threshold": threshold}

        ests = est_df[est_df["parent_neighborhood"] == chosen_hood_name].sort_values(
            "risk_score", ascending=False).head(top_n_establishments)

        mrow = muni_all.loc[muni_all["entity_name"] == chosen_muni_name].iloc[0]
        hrow = hood_all.loc[hood_all["entity_name"] == chosen_hood_name].iloc[0]

        # صمّام الأمان: هل الحي المختار هو فعلًا أعلى CRP على مستوى النظام كله؟
        warning = None
        if not crp_hood_global.empty:
            top_hood = crp_hood_global.iloc[0]
            if top_hood["parent_neighborhood"] != chosen_hood_name:
                warning = (
                    f"يوجد حي بتركّز خطورة أعلى ({top_hood['excess']:.0f} نقطة تجاوز) خارج هذا المسار — "
                    f"{top_hood['parent_neighborhood']} في {_muni_label(top_hood['parent_municipality'])}."
                )

        return {
            "found": True,
            "municipality": mrow.to_dict(),
            "neighborhood": hrow.to_dict(),
            "establishments": ests.to_dict("records"),
            "warning": warning,
            "threshold": threshold,
        }
    finally:
        if should_close:
            c.close()


def get_low_confidence_alerts(min_score: float = None, top: int = 5,
                              db_path: str = None, con=None) -> pd.DataFrame:
    """
    منشآت درجتها عالية لكن ثقتها منخفضة (عدد عينات قليل) — مستبعدة عمدًا من
    التوصية الأساسية (get_recommended_route) عشان ميتلوّثش المسار بضجيج
    إحصائي، لكن معروضة هنا كقسم منفصل صريح — "قد تكون خطيرة، البيانات مش
    كافية للجزم، تحتاج مراجعة يدوية" بدل ما تتخبى تمامًا.
    """
    c, should_close = _resolve(con, db_path)
    try:
        all_est = get_top(level="establishment", n=100000, con=c)
        if all_est.empty:
            return pd.DataFrame()
        threshold = min_score if min_score is not None else _crp_threshold(
            all_est[all_est["confidence"] != "low"]
        )
        alerts = all_est[(all_est["confidence"] == "low") & (all_est["risk_score"] > threshold)]
        return alerts.sort_values("risk_score", ascending=False).head(top).reset_index(drop=True)
    finally:
        if should_close:
            c.close()


def _muni_label(name: str) -> str:
    """
    بعض قيم اسم البلدية أصلًا بادئة بـ 'بلدية' (بلدية شرق بريدة)، وبعضها لأ
    (مواطنين، الجامعة، جمعية البطين الزراعية) — فمنضيفش الكلمة إلا لو ناقصة،
    وإلا هتتكرر ('بلدية بلدية شرق بريدة').
    """
    name = name or ""
    return name if name.startswith("بلدية") else f"بلدية {name}"


def to_route_text(route: dict) -> str:
    """نص عربي كامل للتوصية الهرمية — للعرض في Streamlit/النص."""
    if not route.get("found"):
        return "لا توجد توصية متاحة حاليًا — البيانات غير كافية لتحديد مسار واضح."

    m, h, ests = route["municipality"], route["neighborhood"], route["establishments"]
    lines = [
        f"### 📍 التوصية: {_muni_label(m['entity_name'])} ← حي {h['entity_name']}",
        f"_بلدية بدرجة {m['risk_score']:.0f} — حي بدرجة {h['risk_score']:.0f}_",
        "",
        "**المنشآت الموصى بزيارتها:**",
    ]
    for i, e in enumerate(ests, 1):
        lines.append(f"{i}. **{e['entity_name']}** — درجة {e['risk_score']:.0f}")
        lines.append(f"   {e['reason_ar']}")
    if route.get("warning"):
        lines.append("")
        lines.append(f"⚠️ {route['warning']}")
    return "\n".join(lines)


def to_route_voice(route: dict) -> str:
    """ملخص صوتي مختصر للتوصية الهرمية."""
    if not route.get("found"):
        return "لا توجد توصية تفتيش متاحة حاليًا."
    m, h, ests = route["municipality"], route["neighborhood"], route["establishments"]
    names = "، و".join(e["entity_name"] for e in ests)
    msg = f"التوصية: {_muni_label(m['entity_name'])}، حي {h['entity_name']}، وتحديدًا {names}."
    if route.get("warning"):
        msg += " " + route["warning"]
    return msg


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