#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_risk_scores.py  —  LARS v2 : Risk-Based Inspection Prioritization
=======================================================================
يقرأ من chemistry_tidy، ويبني جدول `risk_scores` المحسوب مسبقًا.
سكريبت مستقل تمامًا — يتشغّل دوريًا (يومي/أسبوعي)، مش وقت السؤال.

المستويات: establishment (رقم الرخصة) | neighborhood (الحى) | municipality (اسم البلدية)

الاستخدام:
    python build_risk_scores.py --inspect          # يفحص السكيما والقيم قبل أي بناء
    python build_risk_scores.py --dry-run          # يحسب ويطبع Top 10 من غير ما يكتب
    python build_risk_scores.py                    # يبني ويكتب جدول risk_scores
    python build_risk_scores.py --violation-basis technical

Engine version: risk-v1
"""

import argparse
import re
import sys
from datetime import datetime

import duckdb
import numpy as np
import pandas as pd

# ============================================================================
# CONFIG — كل ثابت قابل للضبط موجود هنا، مش مبعثر في الكود
# ============================================================================

from pathlib import Path
_HERE = Path(__file__).resolve().parent                 # src/LARS/scripts
DEFAULT_DB = str(_HERE.parent / "data" / "lars_data.duckdb")
SOURCE_TABLE = "chemistry_tidy"
TARGET_TABLE = "risk_scores"
ENGINE_VERSION = "risk-v1"

# Bayesian shrinkage: pseudo-count. m=10 يعني إن منشأة بـ 10 عينات
# بتاخد نص وزنها من سجلها ونص من المتوسط العام.
SHRINKAGE_M = 10.0

# مرساة التطبيع: ضعف المعدل العام = الدرجة الكاملة (1.0).
# ثابتة عمدًا عشان الدرجات تفضل قابلة للمقارنة بين عمليات البناء المختلفة.
ANCHOR_MULT = 2.0

# فجوة التغطية: منحنى أسّي مشبّع. tau=60 يوم.
COVERAGE_TAU_DAYS = 60.0

# الاتجاه: يتحسب على مستوى البلدية فقط (مش المنشأة — العينات قليلة جدًا لكل منشأة)
TREND_WINDOW_DAYS = 60
TREND_MIN_SAMPLES = 30          # أقل من كده => اتجاه محايد (0.5)

# الأوزان — لازم مجموعها 1.0
WEIGHTS = {
    "hist":      0.40,   # سجل المنشأة نفسها
    "commodity": 0.25,   # خطورة المنتجات اللي بتتعامل فيها (leave-one-out)
    "coverage":  0.25,   # فجوة التغطية / آخر عينة
    "trend":     0.10,   # الاتجاه العام (موروث من البلدية)
}

# مستويات الثقة حسب عدد العينات
CONF_HIGH_N = 20
CONF_MED_N = 8

# مرشحات أسماء الأعمدة — السكريبت بيلاقي الموجود منها فعليًا
COLUMN_CANDIDATES = {
    "sample_code":   ["كود العينة", "sample_code"],
    "date":          ["التاريخ", "sample_date", "date"],
    "commodity":     ["اسم العينة", "sample_name", "commodity"],
    "license":       ["رقم الرخصة", "license_no", "license_number"],
    "establishment": ["اسم المنشاة", "اسم المنشأة", "establishment"],
    "neighborhood":  ["الحى", "الحي", "neighborhood"],
    "municipality":  ["اسم البلدية", "municipality"],
    # قرار المطابقة الرسمي (رأي الكيميائي)
    "verdict":       ["sample_result", "نتيجة العينة", "نتيجة العينة Result"],
    # التجاوز الفني للحد (MRL)
    "above_limit":   ["is_above_limit", "exceeds_limit"],
    "is_compliant":  ["is_compliant"],
}

REQUIRED = ["sample_code", "date", "commodity", "neighborhood", "municipality"]

# ============================================================================
# Helpers
# ============================================================================

_AR_NORM = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ـ": ""})


def norm_ar(s):
    """تطبيع خفيف لمفاتيح التجميع النصية — مش بيمس النص المعروض."""
    if s is None or (isinstance(s, float) and np.isnan(s)):
        return None
    s = str(s).translate(_AR_NORM).strip()
    s = re.sub(r"\s+", " ", s)
    return s or None


def q(col):
    """اقتباس اسم عمود عربي بأمان."""
    return '"' + col.replace('"', '""') + '"'


DATE_FORMATS = ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%d/%m/%Y %H:%M:%S"]


def date_expr(con, col):
    """
    عمود التاريخ ممكن يكون TIMESTAMP أو نص (DD/MM/YYYY في بيانات LARS).
    بنرجّع تعبير SQL بيتعامل مع الحالتين — والترتيب مهم: DD/MM قبل MM/DD.
    """
    t = con.execute(f"SELECT typeof({q(col)}) FROM {SOURCE_TABLE} "
                    f"WHERE {q(col)} IS NOT NULL LIMIT 1").fetchone()
    t = (t[0] if t else "VARCHAR").upper()
    if "VARCHAR" in t or "STRING" in t:
        parts = [f"TRY_STRPTIME(CAST({q(col)} AS VARCHAR), '{f}')" for f in DATE_FORMATS]
        parts.append(f"TRY_CAST({q(col)} AS TIMESTAMP)")
        return "COALESCE(" + ", ".join(parts) + ")"
    return f"CAST({q(col)} AS TIMESTAMP)"


def verdict_expr(col):
    """
    قرار المطابقة الرسمي — يدعم العربي والإنجليزي.
    ترتيب الشروط مهم: 'Non-Compliant' فيها 'Compliant' كنص فرعي.
    NULL بيفضل NULL (مش 0) عشان العينات من غير قرار تتعدّ وتتبلّغ.
    """
    v = f"CAST({q(col)} AS VARCHAR)"
    return f"""CASE
        WHEN {q(col)} IS NULL OR TRIM({v}) = '' THEN NULL
        WHEN {v} ILIKE 'non%%'        THEN 1
        WHEN {v} LIKE '%%غير%%'         THEN 1
        WHEN {v} IN ('0','False','false','No','no') THEN 1
        WHEN {v} ILIKE 'compliant%%'  THEN 0
        WHEN {v} LIKE '%%مطابق%%'       THEN 0
        WHEN {v} IN ('1','True','true','Yes','yes') THEN 0
        ELSE NULL END""".replace("%%", "%")


def resolve_columns(con):
    """يحدد أسماء الأعمدة الموجودة فعلًا في chemistry_tidy."""
    actual = [r[0] for r in con.execute(f"DESCRIBE {SOURCE_TABLE}").fetchall()]
    actual_norm = {norm_ar(c): c for c in actual}
    resolved = {}
    for logical, cands in COLUMN_CANDIDATES.items():
        for c in cands:
            if c in actual:
                resolved[logical] = c
                break
            if norm_ar(c) in actual_norm:
                resolved[logical] = actual_norm[norm_ar(c)]
                break
    missing = [k for k in REQUIRED if k not in resolved]
    if missing:
        print(f"❌ أعمدة مطلوبة غير موجودة: {missing}", file=sys.stderr)
        print(f"   الأعمدة المتاحة: {actual}", file=sys.stderr)
        sys.exit(1)
    if not any(k in resolved for k in ("verdict", "above_limit", "is_compliant")):
        print("❌ مفيش أي عمود يحدد المخالفة (sample_result / is_above_limit / is_compliant)",
              file=sys.stderr)
        sys.exit(1)
    return resolved, actual


def inspect(con, cols, actual):
    """وضع الفحص — يطبع كل اللي محتاج تأكيد بشري قبل الثقة في الأرقام."""
    print("=" * 70)
    print("فحص السكيما — chemistry_tidy")
    print("=" * 70)
    print(f"\nالأعمدة الموجودة ({len(actual)}):")
    for c in actual:
        print(f"  - {c}")
    print("\nربط الأعمدة المنطقية:")
    for k in COLUMN_CANDIDATES:
        print(f"  {k:15s} -> {cols.get(k, '❌ غير موجود')}")

    n_rows = con.execute(f"SELECT COUNT(*) FROM {SOURCE_TABLE}").fetchone()[0]
    n_samp = con.execute(
        f"SELECT COUNT(DISTINCT {q(cols['sample_code'])}) FROM {SOURCE_TABLE}").fetchone()[0]
    print(f"\nالصفوف: {n_rows:,} | العينات الفريدة: {n_samp:,}")

    dexpr = date_expr(con, cols["date"])
    dmin, dmax, dbad = con.execute(
        f"SELECT MIN({dexpr}), MAX({dexpr}), SUM(CASE WHEN {dexpr} IS NULL THEN 1 ELSE 0 END) "
        f"FROM {SOURCE_TABLE}").fetchone()
    print(f"المدى الزمني (بعد التحويل): {dmin} → {dmax} | صفوف غير قابلة للتحويل: {dbad}")

    for key in ("verdict", "above_limit", "is_compliant"):
        if key in cols:
            print(f"\nالقيم المميزة في {cols[key]}:")
            df = con.execute(
                f"SELECT {q(cols[key])} AS v, COUNT(*) AS n FROM {SOURCE_TABLE} "
                f"GROUP BY 1 ORDER BY 2 DESC LIMIT 15").df()
            print(df.to_string(index=False))

    if "establishment" in cols:
        raw = con.execute(
            f"SELECT COUNT(DISTINCT {q(cols['establishment'])}) FROM {SOURCE_TABLE}").fetchone()[0]
        print(f"\nاسم المنشاة: {raw:,} صيغة خام مميزة")

    if "license" in cols:
        nulls = con.execute(
            f"SELECT COUNT(*) FROM {SOURCE_TABLE} WHERE {q(cols['license'])} IS NULL "
            f"OR TRIM(CAST({q(cols['license'])} AS VARCHAR)) = ''").fetchone()[0]
        uniq = con.execute(
            f"SELECT COUNT(DISTINCT {q(cols['license'])}) FROM {SOURCE_TABLE}").fetchone()[0]
        print(f"\nرقم الرخصة: {uniq:,} قيمة فريدة | {nulls:,} صف فاضي/NULL")
    else:
        print("\n⚠️  رقم الرخصة غير موجود — مستوى المنشأة هيستخدم الاسم المطبّع "
              "(معرّض للتفتيت الإملائي)")

    print("\n" + "=" * 70)
    print("راجع الأعلى (خصوصًا قيم عمود المخالفة) قبل ما تشغّل البناء.")
    print("=" * 70)


# ============================================================================
# STEP 1 — تسطيح لمستوى العينة (مش الصف!)
# ============================================================================

def build_sample_level(con, cols, basis, est_key="auto"):
    """
    كل صف = عينة واحدة. ده الأساس — العد على مستوى الصف بيضخّم المخالفات
    لأن العينة الواحدة فيها لحد 10 متبقيات.
    """
    dexpr = date_expr(con, cols["date"])

    if basis == "official":
        if "verdict" in cols:
            vio = f"MAX({verdict_expr(cols['verdict'])})"
        elif "is_compliant" in cols:
            vio = f"MAX(CASE WHEN {q(cols['is_compliant'])} = 0 THEN 1 " \
                  f"WHEN {q(cols['is_compliant'])} = 1 THEN 0 ELSE NULL END)"
        else:
            vio = f"MAX(COALESCE(CAST({q(cols['above_limit'])} AS INTEGER), 0))"
    else:  # technical
        if "above_limit" in cols:
            vio = f"MAX(COALESCE(CAST({q(cols['above_limit'])} AS INTEGER), 0))"
        elif "is_compliant" in cols:
            vio = f"MAX(CASE WHEN {q(cols['is_compliant'])} = 0 THEN 1 ELSE 0 END)"
        else:
            raise SystemExit("❌ --violation-basis technical محتاج عمود is_above_limit")

    # العدّاد المقابل (شفافية: الرسمي مقابل الفني)
    alt = "NULL"
    if basis == "official" and "above_limit" in cols:
        alt = f"MAX(COALESCE(CAST({q(cols['above_limit'])} AS INTEGER), 0))"
    elif basis == "technical" and "verdict" in cols:
        alt = f"MAX({verdict_expr(cols['verdict'])})"

    lic = q(cols["license"]) if "license" in cols else "NULL"
    est = q(cols["establishment"]) if "establishment" in cols else "NULL"

    sql = f"""
    CREATE OR REPLACE TEMP VIEW sample_base AS
    WITH parsed AS (
        SELECT *, {dexpr} AS _dt
        FROM {SOURCE_TABLE}
        WHERE {q(cols['sample_code'])} IS NOT NULL
    )
    SELECT
        {q(cols['sample_code'])}                        AS sample_code,
        CAST(MAX(_dt) AS DATE)                          AS sample_date,
        MAX(CAST({q(cols['commodity'])} AS VARCHAR))    AS commodity,
        MAX(CAST({lic} AS VARCHAR))                     AS license_no,
        MAX(CAST({est} AS VARCHAR))                     AS establishment,
        MAX(CAST({q(cols['neighborhood'])} AS VARCHAR)) AS neighborhood,
        MAX(CAST({q(cols['municipality'])} AS VARCHAR)) AS municipality,
        {vio}                                           AS is_violation,
        {alt}                                           AS is_violation_alt,
        COUNT(*)                                        AS n_rows
    FROM parsed
    WHERE _dt IS NOT NULL
    GROUP BY 1
    """
    con.execute(sql)

    n_all = con.execute(
        f"SELECT COUNT(DISTINCT {q(cols['sample_code'])}) FROM {SOURCE_TABLE}").fetchone()[0]
    df = con.execute("SELECT * FROM sample_base").df()
    if len(df) < n_all:
        print(f"⚠️  {n_all - len(df):,} عينة اتستبعدت — تاريخ غير قابل للتحويل")

    no_verdict = int(df["is_violation"].isna().sum())
    if no_verdict:
        print(f"⚠️  {no_verdict:,} عينة من غير قرار مطابقة — بتتعدّ كمطابقة "
              f"({no_verdict / len(df) * 100:.1f}% من العينات)")
    df["is_violation"] = df["is_violation"].fillna(0).astype(int)
    df["is_violation_alt"] = df["is_violation_alt"].fillna(0).astype(int)

    for c in ("commodity", "neighborhood", "municipality", "establishment"):
        df[c + "_key"] = df[c].map(norm_ar)

    def _clean(x):
        return None if x is None or str(x).strip() in ("", "nan", "None", "NULL") else str(x).strip()

    df["license_no"] = df["license_no"].map(_clean)

    # ── مفتاح مستوى المنشأة
    has_lic = df["license_no"].notna().any()
    if est_key == "license" and not has_lic:
        sys.exit("❌ --establishment-key license بس رقم الرخصة مش موجود في الجدول")
    use_license = has_lic if est_key == "auto" else (est_key == "license")
    if use_license:
        df["est_key"] = df["license_no"]
        df.attrs["est_basis"] = "license"
    else:
        df["est_key"] = df["establishment_key"]
        df.attrs["est_basis"] = "name"
        n_names = df["est_key"].nunique()
        n_raw = df["establishment"].nunique()
        print(f"⚠️  رقم الرخصة غير موجود — مستوى المنشأة مفتاحه الاسم المطبّع "
              f"({n_names:,} كيان من {n_raw:,} صيغة اسم خام).")
        print("    خطر تفتيت: نفس المنشأة بإملاء مختلف = كيانين. "
              "الحل الدائم: رجّع رقم الرخصة في transform_chemistry_data.py")
    return df


# ============================================================================
# STEP 2 — المكوّنات الأربعة
# ============================================================================

def shrunk_rate(v, n, p0, m=SHRINKAGE_M):
    """Bayesian shrinkage نحو المعدل العام p0."""
    return (v + m * p0) / (n + m)


def normalize(p, p0):
    """تطبيع نحو مرساة ثابتة: ANCHOR_MULT × المعدل العام = 1.0"""
    if p0 <= 0:
        return 0.0
    return float(np.clip(p / (ANCHOR_MULT * p0), 0.0, 1.0))


def commodity_loo_risk(sdf, p0):
    """
    خطورة المنتجات — leave-one-out.
    خطورة منتج معيّن بالنسبة لمنشأة = محسوبة من سجل *كل الآخرين* مع نفس المنتج.
    ده بيمنع إننا نحسب نفس الدليل مرتين (مرة كسجل المنشأة ومرة كخطورة منتج).
    """
    ct = sdf.groupby("commodity_key").agg(N=("is_violation", "size"),
                                          V=("is_violation", "sum"))
    return ct, p0


def entity_commodity_component(sdf, level_key, ct, p0):
    """متوسط موزون بعدد العينات لخطورة منتجات كل كيان (LOO)."""
    g = sdf.groupby([level_key, "commodity_key"]).agg(
        n_ic=("is_violation", "size"), v_ic=("is_violation", "sum")).reset_index()
    g = g.merge(ct, left_on="commodity_key", right_index=True, how="left")
    N_rest = (g["N"] - g["n_ic"]).clip(lower=0)
    V_rest = (g["V"] - g["v_ic"]).clip(lower=0)
    g["p_loo"] = (V_rest + SHRINKAGE_M * p0) / (N_rest + SHRINKAGE_M)
    g["wsum"] = g["p_loo"] * g["n_ic"]
    agg = g.groupby(level_key).agg(wsum=("wsum", "sum"), n=("n_ic", "sum"))
    out = (agg["wsum"] / agg["n"]).rename("p_commodity")
    # المنتج اللي فعلًا بيرفع المكوّن ده — عشان التفسير يطابق الدرجة
    driver = (g.sort_values("p_loo", ascending=False)
                .groupby(level_key)["commodity_key"].first().rename("driver_commodity"))
    return out, driver


def municipality_trend(sdf, ref_date, p0):
    """
    الاتجاه — على مستوى البلدية فقط.
    5 شهور بيانات + عينات قليلة لكل منشأة = ميل شهري على مستوى المنشأة بيقيس ضوضاء.
    0.5 = محايد، >0.5 = بيسوء، <0.5 = بيتحسن.
    """
    w = pd.Timedelta(days=TREND_WINDOW_DAYS)
    recent = sdf[sdf["sample_date"] > (ref_date - w)]
    prior = sdf[(sdf["sample_date"] <= (ref_date - w)) &
                (sdf["sample_date"] > (ref_date - 2 * w))]

    def rates(d):
        g = d.groupby("municipality_key").agg(n=("is_violation", "size"),
                                              v=("is_violation", "sum"))
        g["p"] = shrunk_rate(g["v"], g["n"], p0)
        return g

    r, pr = rates(recent), rates(prior)
    idx = sdf["municipality_key"].dropna().unique()
    out = pd.Series(0.5, index=idx, dtype=float)
    for m in idx:
        if m in r.index and m in pr.index and \
           r.loc[m, "n"] >= TREND_MIN_SAMPLES and pr.loc[m, "n"] >= TREND_MIN_SAMPLES:
            delta = r.loc[m, "p"] - pr.loc[m, "p"]
            out[m] = float(np.clip(0.5 + delta / (ANCHOR_MULT * p0) if p0 > 0 else 0.5, 0.0, 1.0))
    return out


# ============================================================================
# STEP 3 — تجميع مستوى واحد
# ============================================================================

def score_level(sdf, level, key_col, name_col, p0, ref_date, trend_map, ct):
    d = sdf[sdf[key_col].notna()].copy()
    if d.empty:
        return pd.DataFrame()

    base = d.groupby(key_col).agg(
        total_samples=("sample_code", "nunique"),
        total_rows=("n_rows", "sum"),
        violations=("is_violation", "sum"),
        violations_alt=("is_violation_alt", "sum"),
        first_sample_date=("sample_date", "min"),
        last_sample_date=("sample_date", "max"),
        distinct_commodities=("commodity_key", "nunique"),
    )

    # الاسم المعروض = الأكثر تكرارًا (مش المطبّع)
    disp = d.groupby(key_col)[name_col].agg(
        lambda s: s.dropna().mode().iloc[0] if not s.dropna().empty else None)
    base["entity_name"] = disp

    top_com = d.groupby(key_col)["commodity"].agg(
        lambda s: s.dropna().mode().iloc[0] if not s.dropna().empty else None)
    base["top_commodity"] = top_com

    # أعلى منتج مخالف تحديدًا (للتفسير)
    viol_com = (d[d["is_violation"] == 1].groupby(key_col)["commodity"]
                .agg(lambda s: s.dropna().mode().iloc[0] if not s.dropna().empty else None))
    base["top_violating_commodity"] = viol_com

    if level != "municipality":
        base["parent_municipality"] = d.groupby(key_col)["municipality"].agg(
            lambda s: s.dropna().mode().iloc[0] if not s.dropna().empty else None)
    else:
        base["parent_municipality"] = None
    if level == "establishment":
        base["parent_neighborhood"] = d.groupby(key_col)["neighborhood"].agg(
            lambda s: s.dropna().mode().iloc[0] if not s.dropna().empty else None)
    else:
        base["parent_neighborhood"] = None

    mun_key = d.groupby(key_col)["municipality_key"].agg(
        lambda s: s.dropna().mode().iloc[0] if not s.dropna().empty else None)

    # ── المكوّنات
    base["violation_rate_raw"] = base["violations"] / base["total_samples"]
    p_hist = shrunk_rate(base["violations"], base["total_samples"], p0)
    base["c_hist"] = [normalize(x, p0) for x in p_hist]

    p_com, driver = entity_commodity_component(d, key_col, ct, p0)
    base["c_commodity"] = [normalize(p_com.get(i, p0), p0) for i in base.index]
    disp_map = (d.dropna(subset=["commodity_key"])
                  .drop_duplicates("commodity_key")
                  .set_index("commodity_key")["commodity"].to_dict())
    base["risk_driver_commodity"] = [
        disp_map.get(driver.get(i), driver.get(i)) for i in base.index]

    gap = (pd.Timestamp(ref_date) - pd.to_datetime(base["last_sample_date"])).dt.days
    base["days_since_last_sample"] = gap.astype(int)
    base["c_coverage"] = 1.0 - np.exp(-gap / COVERAGE_TAU_DAYS)

    base["c_trend"] = [float(trend_map.get(mun_key.get(i), 0.5)) for i in base.index]

    # ── الدرجة
    base["risk_score"] = (
        WEIGHTS["hist"] * base["c_hist"] +
        WEIGHTS["commodity"] * base["c_commodity"] +
        WEIGHTS["coverage"] * base["c_coverage"] +
        WEIGHTS["trend"] * base["c_trend"]
    ) * 100.0
    base["risk_score"] = base["risk_score"].round(1)

    base["confidence"] = np.where(base["total_samples"] >= CONF_HIGH_N, "high",
                          np.where(base["total_samples"] >= CONF_MED_N, "medium", "low"))

    for k, v in WEIGHTS.items():
        base["w_" + k] = v

    base = base.sort_values("risk_score", ascending=False)
    base["rank_in_level"] = range(1, len(base) + 1)
    base["level"] = level
    base = base.reset_index().rename(columns={key_col: "entity_id"})
    base["entity_id"] = base["entity_id"].astype(str)
    if level != "establishment":
        base["entity_name"] = base["entity_name"].fillna(base["entity_id"])
    return base


# ============================================================================
# STEP 4 — التفسير (إلزامي، مش اختياري)
# ============================================================================

def build_reasons(df):
    ar, en = [], []
    for _, r in df.iterrows():
        contrib = {
            "hist": WEIGHTS["hist"] * r["c_hist"],
            "commodity": WEIGHTS["commodity"] * r["c_commodity"],
            "coverage": WEIGHTS["coverage"] * r["c_coverage"],
            "trend": WEIGHTS["trend"] * max(r["c_trend"] - 0.5, 0) * 2,
        }
        top = [k for k, _ in sorted(contrib.items(), key=lambda x: -x[1])[:2] if contrib[k] > 0.05]
        pa, pe = [], []
        for k in top:
            if k == "hist":
                pa.append(f"سجل مخالفات {int(r['violations'])} من {int(r['total_samples'])} عينة")
                pe.append(f"{int(r['violations'])} violations in {int(r['total_samples'])} samples")
            elif k == "commodity":
                c = (r.get("risk_driver_commodity") or r.get("top_violating_commodity")
                     or r.get("top_commodity") or "—")
                pa.append(f"منتجات عالية الخطورة تاريخيًا ({c})")
                pe.append(f"historically high-risk commodities ({c})")
            elif k == "coverage":
                pa.append(f"مفيش عينات من {int(r['days_since_last_sample'])} يوم")
                pe.append(f"no samples for {int(r['days_since_last_sample'])} days")
            elif k == "trend":
                pa.append("الاتجاه العام في البلدية بيسوء")
                pe.append("worsening trend in the municipality")
        if not pa:
            pa, pe = ["مؤشرات منخفضة عبر كل المكونات"], ["low signal across all components"]
        tail_a = "" if r["confidence"] != "low" else " ⚠️ عدد عينات قليل — ثقة منخفضة"
        tail_e = "" if r["confidence"] != "low" else " (low sample count — low confidence)"
        ar.append(f"درجة {r['risk_score']:.0f} — " + " + ".join(pa) + tail_a)
        en.append(f"Score {r['risk_score']:.0f} — " + " + ".join(pe) + tail_e)
    df["reason_ar"], df["reason_en"] = ar, en
    return df


# ============================================================================
# MAIN
# ============================================================================

FINAL_COLS = [
    "level", "entity_id", "entity_name", "parent_municipality", "parent_neighborhood",
    "total_samples", "total_rows", "violations", "violations_alt", "violation_rate_raw",
    "first_sample_date", "last_sample_date", "days_since_last_sample",
    "distinct_commodities", "top_commodity", "top_violating_commodity",
    "risk_driver_commodity",
    "c_hist", "c_commodity", "c_coverage", "c_trend",
    "w_hist", "w_commodity", "w_coverage", "w_trend",
    "risk_score", "rank_in_level", "confidence", "reason_ar", "reason_en",
    "violation_basis", "establishment_basis", "computed_at", "data_through", "engine_version",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--inspect", action="store_true", help="افحص السكيما وبس")
    ap.add_argument("--dry-run", action="store_true", help="احسب واطبع من غير كتابة")
    ap.add_argument("--violation-basis", choices=["official", "technical"], default="official",
                    help="official = رأي الكيميائي (sample_result) | technical = تجاوز MRL")
    ap.add_argument("--establishment-key", choices=["auto", "license", "name"], default="auto",
                    help="auto = رقم الرخصة لو موجود، وإلا الاسم المطبّع")
    ap.add_argument("--ref-date", default=None,
                    help="تاريخ المرجع لفجوة التغطية (default: آخر تاريخ في البيانات)")
    args = ap.parse_args()

    read_only = args.inspect or args.dry_run
    con = duckdb.connect(args.db, read_only=read_only)
    cols, actual = resolve_columns(con)

    if args.inspect:
        inspect(con, cols, actual)
        return

    sdf = build_sample_level(con, cols, args.violation_basis, args.establishment_key)
    if sdf.empty:
        sys.exit("❌ مفيش عينات صالحة")

    data_through = sdf["sample_date"].max()
    ref_date = pd.Timestamp(args.ref_date) if args.ref_date else pd.Timestamp(data_through)

    p0 = float(sdf["is_violation"].mean())
    print(f"📊 عينات: {len(sdf):,} | معدل المخالفات العام (p0): {p0:.4f} "
          f"| أساس المخالفة: {args.violation_basis}")
    print(f"📅 البيانات حتى: {data_through} | تاريخ المرجع: {ref_date.date()}")
    if ref_date > pd.Timestamp(data_through) + pd.Timedelta(days=30):
        print("⚠️  تاريخ المرجع متأخر كتير عن آخر بيانات — فجوة التغطية هتبقى مشبّعة للكل")

    ct, _ = commodity_loo_risk(sdf, p0)
    trend_map = municipality_trend(sdf, ref_date, p0).to_dict()

    frames = []
    levels = [
        ("neighborhood", "neighborhood_key", "neighborhood"),
        ("municipality", "municipality_key", "municipality"),
    ]
    if sdf["est_key"].notna().any():
        levels.insert(0, ("establishment", "est_key", "establishment"))
        dropped = int(sdf["est_key"].isna().sum())
        if dropped:
            print(f"ℹ️  {dropped:,} عينة من غير مفتاح منشأة — مستثناة من مستوى المنشأة فقط")
    else:
        print("⚠️  مفيش مفتاح صالح للمنشأة — المستوى ده اتشال")

    for level, key, name in levels:
        f = score_level(sdf, level, key, name, p0, ref_date, trend_map, ct)
        if not f.empty:
            frames.append(f)
            print(f"✅ {level:15s}: {len(f):,} كيان")

    out = pd.concat(frames, ignore_index=True)
    out = build_reasons(out)
    out["violation_basis"] = args.violation_basis
    out["computed_at"] = datetime.now()
    out["data_through"] = pd.Timestamp(data_through)
    out["engine_version"] = ENGINE_VERSION
    out["establishment_basis"] = sdf.attrs.get("est_basis", "n/a")
    for c in FINAL_COLS:
        if c not in out.columns:
            out[c] = None
    out = out[FINAL_COLS]

    print("\n" + "=" * 70)
    print("أعلى 10 منشآت أولوية")
    print("=" * 70)
    est = out[out["level"] == "establishment"].head(10)
    show = est if not est.empty else out.head(10)
    for _, r in show.iterrows():
        print(f"{r['rank_in_level']:2d}. [{r['risk_score']:5.1f}] {r['entity_name']}")
        print(f"    {r['reason_ar']}")
        print(f"    تاريخ={r['c_hist']:.2f} منتج={r['c_commodity']:.2f} "
              f"تغطية={r['c_coverage']:.2f} اتجاه={r['c_trend']:.2f} | ثقة={r['confidence']}")

    if args.dry_run:
        print("\n(dry-run — مفيش كتابة)")
        return

    reg = out.copy()
    for c in reg.columns:                      # توافق pandas 3.x مع duckdb register
        if reg[c].dtype.kind in "OU" or str(reg[c].dtype) == "str":
            reg[c] = reg[c].astype(object)
    con.register("risk_df", reg)
    con.execute(f"CREATE OR REPLACE TABLE {TARGET_TABLE} AS SELECT * FROM risk_df")
    con.execute(f"CREATE INDEX IF NOT EXISTS idx_risk_level ON {TARGET_TABLE}(level)")
    n = con.execute(f"SELECT COUNT(*) FROM {TARGET_TABLE}").fetchone()[0]
    con.close()
    print(f"\n✅ اتكتب {TARGET_TABLE}: {n:,} صف")


if __name__ == "__main__":
    main()