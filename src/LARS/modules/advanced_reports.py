# -*- coding: utf-8 -*-
"""
LARS — Advanced Reports (modules/advanced_reports.py)
========================================================
Generalized seasonal compliance report engine, driven by the live
`chemistry_tidy` table for ANY commodity (اسم العينة), not a single
uploaded file. Add one line to app_new.py's PAGES dict:

    "📑 التقارير المتقدمة": "modules.advanced_reports:show_advanced_reports_page",

WHY THIS IS SIMPLER THAN THE ORIGINAL PROTOTYPE
--------------------------------------------------
chemistry_tidy is already ETL-cleaned: pesticide_name is English and
canonical (no typo/alias resolution needed here — that belongs in the
ETL step, not the report layer), concentration/limit_value are numeric.
What's left to handle at the report layer:
  1. sample_result is the lab's own verdict — use it as ground truth for
     "Violated / Compliant" counts, never re-derive compliance from raw
     concentration > limit_value (that re-derivation was the exact bug
     found during the cucumber prototype — see Verdict Reconciliation).
  2. limit_value can still carry data-entry noise (typos, superseded
     MRL standards) even after ETL — canonicalize per (commodity,
     pesticide) group before using it for exceed-rate/IqR diagnostics.
  3. Category mapping (Insecticide/Fungicide/...) isn't in the schema —
     kept as a lookup dict here; move to a `pesticide_reference` table
     when convenient.
"""

import io
from collections import Counter

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ---------------------------------------------------------------------------
# DB connection — adjust this import if your data_access.py exposes a
# differently-named function. get_duckdb_write() is used elsewhere in the
# app (see inspection_priority.py) so it's reused here for consistency;
# this page only ever reads.
# ---------------------------------------------------------------------------
try:
    from modules.data_access import get_duckdb_write as _get_conn
except ImportError:
    import os
    import duckdb

    def _get_conn():
        path = os.environ.get(
            "LARS_DUCKDB_PATH",
            os.path.join(os.path.dirname(__file__), "..", "data", "lars_data_demo.duckdb"),
        )
        return duckdb.connect(path, read_only=True)


SEASON_CASE_SQL = """
    CASE
        WHEN CAST(strftime(sample_date_parsed, '%m') AS INT) IN (12,1,2) THEN 'Winter'
        WHEN CAST(strftime(sample_date_parsed, '%m') AS INT) IN (3,4,5)  THEN 'Spring'
        WHEN CAST(strftime(sample_date_parsed, '%m') AS INT) IN (6,7,8)  THEN 'Summer'
        ELSE 'Autumn'
    END
"""
SEASON_ORDER = ["Winter", "Spring", "Summer", "Autumn"]

# Facilities excluded from all verdict/compliance calculations — these are
# referral/institutional entries, not commercial establishments subject to
# inspection, so they shouldn't count toward compliance-rate or facility
# scorecard statistics. Matched with LIKE so partial/suffixed name variants
# (e.g. "الجامعة" appearing inside a longer facility string) are also caught.
EXCLUDED_FACILITY_PATTERNS = [
    "جمعية البطين الزراعية",
    "الجامعة",
]

IQR_BINS = [
    ("0", "Excellent", lambda v: v == 0),
    ("0-0.6", "Good", lambda v: 0 < v <= 0.6),
    ("0.6-1.0", "Adequate", lambda v: 0.6 < v <= 1.0),
    (">1.0", "Inadequate", lambda v: v > 1.0),
]

# Move to a real pesticide_reference table when convenient — kept here for
# now since chemistry_tidy has no category column.
CATEGORY = {
    **{p: "Insecticide" for p in [
        "acetamiprid", "imidacloprid", "thiamethoxam", "clothianidin",
        "dinotefuran", "sulfoxaflor", "thiacloprid", "chlorpyrifos",
        "profenofos", "ethion", "diazinon", "dimethoate", "omethoate",
        "malathion", "fenitrothion", "pirimiphos-methyl", "sulfotep",
        "methomyl", "carbaryl", "carbofuran", "oxamyl", "cypermethrin",
        "cyfluthrin", "deltamethrin", "lambda-cyhalothrin", "bifenthrin",
        "fenpropathrin", "esfenvalerate", "etofenprox", "indoxacarb",
        "chlorantraniliprole", "cyantraniliprole", "emamectin benzoate",
        "spinosad", "spinetoram", "methoxyfenozide", "buprofezin",
        "pyriproxyfen", "chlorfenapyr", "metaflumizone", "fipronil",
        "chlorfluazuron", "pirimicarb", "spirotetramat", "tolfenpyrad",
    ]},
    **{p: "Acaricide" for p in [
        "abamectin", "bifenazate", "etoxazole", "hexythiazox", "pyridaben",
        "cyflumetofen", "fenpyroximate", "spirodiclofen", "propargite",
        "tebufenpyrad", "spiromesifen",
    ]},
    **{p: "Fungicide" for p in [
        "azoxystrobin", "pyraclostrobin", "trifloxystrobin", "boscalid",
        "carbendazim", "thiophanate-methyl", "tebuconazole",
        "difenoconazole", "propiconazole", "penconazole", "myclobutanil",
        "flutriafol", "cyproconazole", "flusilazole", "triflumizole",
        "metalaxyl", "dimethomorph", "mandipropamid", "propamocarb",
        "cyazofamid", "fludioxonil", "cyprodinil", "pyrimethanil",
        "fenhexamid", "famoxadone", "metrafenone", "cyflufenamid",
        "zoxamide", "pydiflumetofen", "thiabendazole", "tricyclazole",
        "flutolanil", "ethirimol", "iprovalicarb", "biphenyl", "fluopyram",
    ]},
    **{p: "Herbicide" for p in [
        "alachlor", "linuron", "metribuzin", "oxadiazon", "pretilachlor",
        "ethofumesate", "chlorpropham",
    ]},
    **{p: "Nematicide" for p in ["cadusafos"]},
    **{p: "Other" for p in ["piperonyl butoxide", "diphenylamine"]},
}


# =============================================================================
# Data layer
# =============================================================================

def _excluded_facility_sql(where, params):
    """Appends NOT LIKE clauses for EXCLUDED_FACILITY_PATTERNS onto an
    existing where-clause list/params pair, in place."""
    for pattern in EXCLUDED_FACILITY_PATTERNS:
        where.append('"اسم المنشاة" NOT LIKE ?')
        params.append(f"%{pattern}%")


@st.cache_data(ttl=600, show_spinner=False)
def load_residues(commodities=None, year=None):
    """One row per (sample_code, pesticide_name) detection, joined with the
    sample's own lab verdict. commodities=None means all commodities."""
    con = _get_conn()
    where = ["is_detected = 1", '"التاريخ" IS NOT NULL']
    params = []
    if commodities:
        placeholders = ",".join(["?"] * len(commodities))
        where.append(f'"اسم العينة" IN ({placeholders})')
        params += list(commodities)
    if year:
        where.append("CAST(strftime(sample_date_parsed, '%Y') AS INT) = ?")
        params.append(year)
    _excluded_facility_sql(where, params)
    where_sql = " AND ".join(where)

    sql = f"""
        WITH parsed AS (
            SELECT *,
                   strptime("التاريخ", '%d/%m/%Y') AS sample_date_parsed
            FROM chemistry_tidy
        )
        SELECT
            "كود العينة"       AS sample_code,
            "اسم العينة"       AS commodity,
            {SEASON_CASE_SQL}   AS season,
            CAST(strftime(sample_date_parsed, '%Y') AS INT) AS year,
            pesticide_name,
            concentration,
            limit_value,
            sample_result,
            "اسم المنشاة"      AS facility,
            "اسم البلدية"      AS municipality
        FROM parsed
        WHERE {where_sql}
    """
    df = con.execute(sql, params).df()
    con.close()
    return df


@st.cache_data(ttl=600, show_spinner=False)
def load_all_samples(commodities=None, year=None):
    """One row per sample (including pesticide-free samples), with verdict."""
    con = _get_conn()
    where = ['"التاريخ" IS NOT NULL']
    params = []
    if commodities:
        placeholders = ",".join(["?"] * len(commodities))
        where.append(f'"اسم العينة" IN ({placeholders})')
        params += list(commodities)
    if year:
        where.append("CAST(strftime(sample_date_parsed, '%Y') AS INT) = ?")
        params.append(year)
    _excluded_facility_sql(where, params)
    where_sql = " AND ".join(where)

    sql = f"""
        WITH parsed AS (
            SELECT *,
                   strptime("التاريخ", '%d/%m/%Y') AS sample_date_parsed
            FROM chemistry_tidy
        )
        SELECT
            "كود العينة"  AS sample_code,
            "اسم العينة"  AS commodity,
            {SEASON_CASE_SQL} AS season,
            CAST(strftime(sample_date_parsed, '%Y') AS INT) AS year,
            "اسم المنشاة" AS facility,
            "اسم البلدية" AS municipality,
            MAX(sample_result)      AS lab_verdict,
            SUM(is_detected)        AS n_pesticides
        FROM parsed
        WHERE {where_sql}
        GROUP BY 1,2,3,4,5,6
    """
    df = con.execute(sql, params).df()
    con.close()
    df["lab_non_compliant"] = df["lab_verdict"].astype(str).str.contains(
        "Non-Compliant", case=False, na=False
    )
    df["n_pesticides"] = df["n_pesticides"].fillna(0).astype(int)
    return df


def canonicalize_mrl(residues):
    """Per (commodity, pesticide): dominant MRL wins; a minority value seen
    in <=2 samples that's a clean power-of-10 shift of the dominant is a
    typo and gets corrected; a minority value seen in >2 samples is treated
    as a legitimate historical/alternate standard and kept as recorded."""
    r = residues.dropna(subset=["limit_value"]).copy()
    r["mrl_canonical"] = r["limit_value"]
    r["mrl_note"] = ""
    for (commodity, pest), g in r.groupby(["commodity", "pesticide_name"]):
        vc = g["limit_value"].value_counts()
        if len(vc) <= 1:
            continue
        dominant = vc.idxmax()
        for val, cnt in vc.items():
            if val == dominant:
                continue
            ratio = val / dominant if dominant else None
            is_shift = ratio is not None and any(
                abs(ratio - k) < 0.05 for k in [10, 100, 0.1, 0.01]
            )
            mask = (r["commodity"] == commodity) & (r["pesticide_name"] == pest) & (r["limit_value"] == val)
            if cnt <= 2 and is_shift:
                r.loc[mask, "mrl_canonical"] = dominant
                r.loc[mask, "mrl_note"] = f"typo corrected: {val} -> {dominant}"
            elif cnt > 2:
                r.loc[mask, "mrl_note"] = f"alternate/historical MRL kept (n={cnt})"
            else:
                r.loc[mask, "mrl_note"] = f"ambiguous MRL (n={cnt}) — needs review"
    residues = residues.merge(
        r[["sample_code", "pesticide_name", "mrl_canonical", "mrl_note"]],
        on=["sample_code", "pesticide_name"], how="left",
    )
    return residues


# =============================================================================
# Table builders (per selected scope: could be one commodity, several, or all)
# =============================================================================

def t1_seasonal_summary(samples):
    rows = []
    for season in SEASON_ORDER:
        s = samples[samples["season"] == season]
        if s.empty:
            continue
        total = len(s)
        free = int((s["n_pesticides"] == 0).sum())
        with_res = total - free
        viol = int(s["lab_non_compliant"].sum())
        below = total - free - viol
        pct = lambda n: f"{n} ({n / total * 100:.1f}%)"
        rows.append([season, total, pct(free), pct(with_res), pct(viol), pct(below)])
    return pd.DataFrame(rows, columns=["Season", "Total", "Pesticide-free",
                                       "With residues", "Violated (lab verdict)",
                                       "Residues ≤MRL"])


def t2_distribution(samples, max_n=7):
    """Histogram of number of pesticides detected per sample, per season."""
    out = {}
    for season in SEASON_ORDER:
        s = samples[samples["season"] == season]
        if s.empty:
            continue
        total = len(s)
        counts = Counter(int(v) for v in s["n_pesticides"])
        top = int(max(max_n, max(counts) if counts else 0))
        rows = [[k, counts.get(k, 0), round(counts.get(k, 0) / total * 100, 1)]
                for k in range(top + 1)]
        out[season] = pd.DataFrame(rows, columns=["No. of pesticides in sample",
                                                  "Samples (n)", "Samples (%)"])
    return out


def t3_pesticide_detail(residues_c):
    """Per-pesticide diagnostic stats per season: frequency, exceed rate
    (using canonicalized MRL), min-max, mean concentration. Diagnostic
    only — NOT the compliance verdict, which stays sourced from
    sample_result (see t1_seasonal_summary)."""
    out = {}
    r = residues_c.dropna(subset=["concentration"])
    for season in SEASON_ORDER:
        s = r[r["season"] == season]
        if s.empty:
            continue
        rows = []
        for name, g in s.groupby("pesticide_name"):
            freq = len(g)
            known = g.dropna(subset=["mrl_canonical"])
            exceed = int((known["concentration"] > known["mrl_canonical"]).sum())
            mrl_vals = known["mrl_canonical"].unique()
            rows.append([
                name, freq, f"{exceed} ({exceed / freq * 100:.1f}%)" if freq else "0 (0%)",
                f"{g['concentration'].min():.3f}-{g['concentration'].max():.3f}",
                round(g["concentration"].mean(), 6),
                mrl_vals[0] if len(mrl_vals) == 1 else
                ("/".join(str(v) for v in sorted(mrl_vals)) if len(mrl_vals) else ""),
            ])
        d = pd.DataFrame(rows, columns=["Pesticide", "Frequency (n)", "Exceed (n, %)",
                                        "Min-Max Concentration (mg/kg)",
                                        "Mean Concentration (mg/kg)", "MRL (mg/kg)"])
        out[season] = d.sort_values("Frequency (n)", ascending=False).reset_index(drop=True)
    return out


def t4_iqr(samples, residues_c):
    r = residues_c.dropna(subset=["concentration", "mrl_canonical"])
    r = r[r["mrl_canonical"] != 0]
    iqr = (r["concentration"] / r["mrl_canonical"]).groupby(r["sample_code"]).sum()
    s = samples.set_index("sample_code")
    s["iqr"] = iqr.reindex(s.index).fillna(0.0)
    rows = []
    seasons = [se for se in SEASON_ORDER if (s["season"] == se).any()]
    for rng, label, pred in IQR_BINS:
        row = [rng, label]
        for season in seasons:
            ss = s[s["season"] == season]
            n = int(ss["iqr"].apply(pred).sum())
            row += [n, round(n / len(ss) * 100, 1) if len(ss) else 0]
        rows.append(row)
    cols = ["IqR range", "Quality category"]
    for season in seasons:
        cols += [f"{season} No", f"{season} %"]
    return pd.DataFrame(rows, columns=cols), s.reset_index()


def t5_categories(residues):
    r = residues.copy()
    r["category"] = r["pesticide_name"].str.lower().map(CATEGORY).fillna("Unclassified")
    seasons = [s for s in SEASON_ORDER if (r["season"] == s).any()]
    rows = []
    for cat in sorted(r["category"].unique()):
        g = r[r["category"] == cat]
        row = [cat] + [int((g["season"] == s).sum()) for s in seasons] + [len(g)]
        rows.append(row)
    return pd.DataFrame(rows, columns=["Category"] + seasons + ["Overall"])


def t_facility_scorecard(samples, samples_iqr, min_samples=5,
                         inadequate_watch_threshold=0.20, inadequate_risky_threshold=0.35,
                         violation_risky_threshold_pct=10.0):
    """Derived report 1: rank facilities by non-compliance rate AND by
    cumulative residue burden (IqR), for inspection targeting.

    Why combine the two: violation rate alone can miss a facility whose
    samples are all individually 'compliant' but consistently carry a
    heavy multi-residue load (high IqR) — that facility is quietly
    trending toward violations without showing up on the violation-rate
    column at all. IqR alone can't distinguish 'one bad sample' from
    'this facility is systemically risky'. Combining both surfaces three
    categories a manager can act on differently:

      Healthy — no violations, low inadequate-IqR rate
      Watch   — no violations YET, but an elevated inadequate-IqR rate —
                the leading indicator worth a proactive visit
      Risky   — has actual violations, or a high inadequate-IqR rate
                regardless of violation history

    Only facilities with enough volume to be statistically meaningful are
    classified (avoids a single bad sample making a low-volume facility
    look catastrophic).
    """
    s = samples.merge(samples_iqr[["sample_code", "iqr"]], on="sample_code", how="left")
    g = s.groupby("facility").agg(
        total_samples=("sample_code", "count"),
        violations=("lab_non_compliant", "sum"),
        municipality=("municipality", "first"),
        excellent_n=("iqr", lambda x: (x == 0).sum()),
        inadequate_n=("iqr", lambda x: (x > 1.0).sum()),
        mean_iqr=("iqr", "mean"),
    ).reset_index()
    g = g[g["total_samples"] >= min_samples].copy()
    g["violation_rate_pct"] = (g["violations"] / g["total_samples"] * 100).round(1)
    g["excellent_rate_pct"] = (g["excellent_n"] / g["total_samples"] * 100).round(1)
    g["inadequate_rate_pct"] = (g["inadequate_n"] / g["total_samples"] * 100).round(1)
    g["mean_iqr"] = g["mean_iqr"].round(2)

    def classify(row):
        has_violations = row["violation_rate_pct"] > 0
        inadequate_frac = row["inadequate_n"] / row["total_samples"]
        if has_violations and (row["violation_rate_pct"] >= violation_risky_threshold_pct
                               or inadequate_frac >= inadequate_risky_threshold):
            return "Risky"
        if not has_violations and inadequate_frac >= inadequate_risky_threshold:
            return "Risky"
        if not has_violations and inadequate_frac >= inadequate_watch_threshold:
            return "Watch"
        if has_violations:
            return "Watch"
        return "Healthy"

    g["classification"] = g.apply(classify, axis=1)
    g = g.drop(columns=["excellent_n", "inadequate_n"])
    g = g[["facility", "municipality", "total_samples", "violation_rate_pct",
          "excellent_rate_pct", "inadequate_rate_pct", "mean_iqr", "classification"]]

    order = {"Risky": 0, "Watch": 1, "Healthy": 2}
    g["_sort"] = g["classification"].map(order)
    g = g.sort_values(["_sort", "violation_rate_pct", "inadequate_rate_pct"],
                      ascending=[True, False, False]).drop(columns="_sort")
    return g.reset_index(drop=True)


def t_pesticide_watchlist(residues_c, min_n=5):
    """Derived report 2: pesticides whose exceed rate is rising between
    the two most recent seasons present in the data — an early-warning
    signal before it shows up as a compliance crisis."""
    r = residues_c.dropna(subset=["concentration", "mrl_canonical"])
    r = r.assign(exceeds=r["concentration"] > r["mrl_canonical"])
    seasons_present = [s for s in SEASON_ORDER if (r["season"] == s).any()]
    if len(seasons_present) < 2:
        return pd.DataFrame(columns=["Pesticide", "Prior season rate %",
                                     "Latest season rate %", "Delta pp"])
    prior, latest = seasons_present[-2], seasons_present[-1]
    rows = []
    for pest, g in r.groupby("pesticide_name"):
        gp = g[g["season"] == prior]
        gl = g[g["season"] == latest]
        if len(gp) < min_n or len(gl) < min_n:
            continue
        rate_p = gp["exceeds"].mean() * 100
        rate_l = gl["exceeds"].mean() * 100
        rows.append([pest, round(rate_p, 1), round(rate_l, 1), round(rate_l - rate_p, 1)])
    d = pd.DataFrame(rows, columns=["Pesticide", f"{prior} rate %", f"{latest} rate %", "Delta pp"])
    return d.sort_values("Delta pp", ascending=False).reset_index(drop=True)


# =============================================================================
# Excel export
# =============================================================================

def build_workbook_bytes(label, tables):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    HDR_FILL = PatternFill("solid", fgColor="1F3864")
    HDR_FONT = Font(bold=True, color="FFFFFF", size=10)
    BODY = Font(size=10)
    TITLE = Font(bold=True, size=12)
    THIN = Border(*[Side(style="thin", color="B0B0B0")] * 4)

    wb = Workbook()
    wb.remove(wb.active)

    def dump(ws, df, start_row, title):
        r = start_row
        ws.cell(r, 1, title).font = TITLE
        r += 1
        for j, c in enumerate(df.columns, 1):
            cell = ws.cell(r, j, c)
            cell.font, cell.fill, cell.border = HDR_FONT, HDR_FILL, THIN
            cell.alignment = Alignment(horizontal="center", wrap_text=True)
        for _, row in df.iterrows():
            r += 1
            for j, v in enumerate(row, 1):
                cell = ws.cell(r, j, v)
                cell.font, cell.border = BODY, THIN
        for j, c in enumerate(df.columns, 1):
            w = max(len(str(c)), *(len(str(v)) for v in df[c])) + 3 if len(df) else len(str(c)) + 3
            ws.column_dimensions[get_column_letter(j)].width = min(w, 34)
        return r + 2

    for name, content in tables.items():
        ws = wb.create_sheet(name[:31])
        if isinstance(content, dict):
            r = 1
            for season, df in content.items():
                r = dump(ws, df, r, f"{label} — {name} — {season}")
        else:
            dump(ws, content, 1, f"{label} — {name}")

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


# =============================================================================
# Streamlit page
# =============================================================================

def _kpi_card(col, label, value, color="var(--text-primary)"):
    col.markdown(
        f"""<div style="background:#F1EFE8;border-radius:8px;padding:1rem;">
        <p style="font-size:13px;color:#5F5E5A;margin:0 0 4px;">{label}</p>
        <p style="font-size:24px;font-weight:600;margin:0;color:{color};">{value}</p>
        </div>""",
        unsafe_allow_html=True,
    )


def show_advanced_reports_page(api_client=None):
    # api_client is unused here — this page reads directly from DuckDB — but
    # app_new.py's router calls every page as page_func(api_client), so the
    # parameter has to exist even if this page doesn't need it.
    st.markdown("## 📑 Advanced Reports — التقارير المتقدمة")
    st.caption("Seasonal compliance analytics generated directly from chemistry_tidy — any commodity, any season, in one click.")

    con = _get_conn()
    commodities_all = sorted(
        con.execute('SELECT DISTINCT "اسم العينة" FROM chemistry_tidy WHERE "اسم العينة" IS NOT NULL').df()["اسم العينة"]
    )
    years_all = sorted(
        con.execute("""
            SELECT DISTINCT CAST(strftime(strptime("التاريخ", '%d/%m/%Y'), '%Y') AS INT) AS y
            FROM chemistry_tidy WHERE "التاريخ" IS NOT NULL
        """).df()["y"].dropna().astype(int)
    )
    con.close()

    col_a, col_b, col_c = st.columns([2, 1, 1])
    with col_a:
        selected = st.multiselect("Commodity — اسم العينة", options=commodities_all,
                                  default=commodities_all[:1] if commodities_all else [])
    with col_b:
        all_commodities = st.checkbox("All commodities", value=False)
    with col_c:
        year = st.selectbox("Year", options=["All"] + years_all, index=0)

    commodities = None if all_commodities else (selected or None)
    year_val = None if year == "All" else int(year)

    if commodities is None and not all_commodities:
        st.info("Select at least one commodity, or check 'All commodities'.")
        return

    with st.spinner("Loading and analyzing samples..."):
        residues = load_residues(commodities, year_val)
        samples = load_all_samples(commodities, year_val)

    if samples.empty:
        st.warning("No samples found for this selection.")
        return

    residues_c = canonicalize_mrl(residues)
    t4, samples_iqr = t4_iqr(samples, residues_c)
    t1 = t1_seasonal_summary(samples)
    t2 = t2_distribution(samples)
    t3 = t3_pesticide_detail(residues_c)
    t5 = t5_categories(residues)

    total = len(samples)
    viol = int(samples["lab_non_compliant"].sum())
    compliance_rate = round((1 - viol / total) * 100, 1) if total else 0
    k1, k2, k3 = st.columns(3)
    _kpi_card(k1, "Samples analyzed", f"{total:,}")
    _kpi_card(k2, "Compliance rate", f"{compliance_rate}%",
              "#173404" if compliance_rate >= 95 else "#412402")
    _kpi_card(k3, "Non-compliant (lab verdict)", f"{viol}",
              "#501313" if viol else "#173404")

    st.write("")
    show_charts = st.checkbox("Show trend charts", value=True)
    if show_charts:
        cc1, cc2 = st.columns(2)
        with cc1:
            iqr_long = t4.melt(id_vars=["IqR range", "Quality category"],
                               value_vars=[c for c in t4.columns if c.endswith(" No")],
                               var_name="Season", value_name="Samples")
            iqr_long["Season"] = iqr_long["Season"].str.replace(" No", "")
            fig = px.bar(iqr_long, x="Quality category", y="Samples", color="Season",
                        barmode="group", title="IqR quality index by season")
            st.plotly_chart(fig, use_container_width=True)
        with cc2:
            cat_seasons = [c for c in t5.columns if c not in ("Category", "Overall")]
            cat_long = t5.melt(id_vars=["Category"], value_vars=cat_seasons,
                               var_name="Season", value_name="Detections")
            fig2 = px.bar(cat_long, x="Category", y="Detections", color="Season",
                         barmode="group", title="Pesticide category detections")
            st.plotly_chart(fig2, use_container_width=True)

    st.write("")
    tabs = st.tabs(["Seasonal summary", "Residue distribution", "Pesticide detail",
                    "IqR quality index", "Category breakdown",
                    "Facility risk scorecard", "Pesticide watchlist"])

    with tabs[0]:
        st.dataframe(t1, use_container_width=True, hide_index=True)
    with tabs[1]:
        st.caption("Number of pesticides detected per sample, per season.")
        for season, df in t2.items():
            st.markdown(f"**{season}**")
            st.dataframe(df, use_container_width=True, hide_index=True)
    with tabs[2]:
        st.caption("Per-pesticide frequency, exceed rate, and concentration stats. Diagnostic only — the compliance verdict in 'Seasonal summary' always comes from the lab's own sample_result, not this table.")
        for season, df in t3.items():
            st.markdown(f"**{season}**")
            st.dataframe(df, use_container_width=True, hide_index=True)
    with tabs[3]:
        st.dataframe(t4, use_container_width=True, hide_index=True)
    with tabs[4]:
        st.dataframe(t5, use_container_width=True, hide_index=True)
    with tabs[5]:
        st.caption("Facilities with ≥5 samples, classified by combining violation history with cumulative residue burden (IqR): Healthy = no violations and low inadequate-IqR rate. Watch = no violations yet, but an elevated inadequate-IqR rate — a leading indicator worth a proactive visit before it becomes a violation. Risky = has violations, or a high inadequate-IqR rate regardless of violation history.")
        scorecard = t_facility_scorecard(samples, samples_iqr)
        st.dataframe(scorecard, use_container_width=True, hide_index=True)
    with tabs[6]:
        st.caption("Pesticides whose exceed rate rose between the two most recent seasons present — an early-warning signal.")
        watchlist = t_pesticide_watchlist(residues_c)
        if watchlist.empty:
            st.info("Not enough seasons with sufficient volume yet to compute a trend.")
        else:
            st.dataframe(watchlist, use_container_width=True, hide_index=True)

    st.write("")
    label = "All commodities" if all_commodities else ", ".join(commodities)
    wb = build_workbook_bytes(label, {
        "1_Seasonal_Summary": t1,
        "2_Residue_Distribution": t2,
        "3_Pesticide_Detail": t3,
        "4_IqR_Quality_Index": t4,
        "5_Categories": t5,
        "6_Facility_Scorecard": t_facility_scorecard(samples, samples_iqr),
        "7_Pesticide_Watchlist": t_pesticide_watchlist(residues_c),
    })
    st.download_button(
        "⬇️ Download full report (Excel)", data=wb,
        file_name=f"Advanced_Report_{label.replace(', ', '_')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )