"""
LARS :: Food-Poisoning Incident Register (حالات التسمم الغذائي)
================================================================
Ingest + normalisation layer for the municipal poisoning-incident sheet.

Drop-in for the existing LARS DuckDB pipeline:

    from poisoning_ingest import ingest_poisoning_workbook
    ingest_poisoning_workbook("data/raw/halat_tasammum_2026.xlsx", con)

Design notes
------------
* The source sheet is hand-typed by municipal inspectors, so EVERY text
  column is normalised (hamza / alef / taa-marbuta / tatweel / Arabic-Indic
  digits) before it reaches DuckDB. Without this, "اسرة واحدة" and
  "أسرة واحدة" are two different GROUP BY keys.
* `فترة الحضانة` is a mixed column: sometimes a number (16), sometimes free
  Arabic text ("3 ساعات 30 دقيقة"). It is parsed to a single FLOAT
  `incubation_hours`, with the raw string kept for audit (ISO 17025 habit:
  never destroy the source value).
* License number is stored as TEXT. It is an identifier, not a quantity —
  storing it as BIGINT loses leading zeros and invites accidental SUM().
* Nothing here invents a committee decision. The rule engine produces an
  *advisory* attribution flag and the epidemiological agent class; the
  official `committee_decision` column is always kept separate so you can
  measure agreement between LARS and the committee.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

try:                                    # package import
    from .llm_fallback import lookup_with_fallback
except ImportError:                     # direct execution: python ingest.py
    from llm_fallback import lookup_with_fallback
# ---------------------------------------------------------------------------
# 1. Arabic text normalisation
# ---------------------------------------------------------------------------

_ARABIC_INDIC = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_DIACRITICS = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")
_TATWEEL = "\u0640"


def normalize_ar(text: object) -> Optional[str]:
    """Fold Arabic orthographic variants so GROUP BY behaves."""
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return None
    s = str(text)
    s = unicodedata.normalize("NFKC", s)
    s = s.translate(_ARABIC_INDIC)
    s = _DIACRITICS.sub("", s).replace(_TATWEEL, "")
    s = (
        s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
         .replace("ى", "ي").replace("ة", "ه")
         .replace("ؤ", "و").replace("ئ", "ي")
    )
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def display_ar(text: object) -> Optional[str]:
    """Light clean only — keeps the original spelling for the UI."""
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return None
    s = unicodedata.normalize("NFKC", str(text)).replace(_TATWEEL, "")
    return re.sub(r"\s+", " ", s).strip() or None


# ---------------------------------------------------------------------------
# 2. Incubation-period parser  ("3 ساعات 30 دقيقة" -> 3.5)
# ---------------------------------------------------------------------------

_HOUR_WORDS = r"(?:ساعات|ساعه|ساعة|ساعتين|ساعتان|ساعا|س|hr|hrs|hour|hours|h)"
_MIN_WORDS = r"(?:دقائق|دقيقه|دقيقة|دقيقتين|د|min|mins|minute|minutes|m)"
_DAY_WORDS = r"(?:ايام|أيام|يوم|يومين|day|days|d)"


def parse_incubation_hours(value: object) -> Optional[float]:
    """
    Return incubation period in decimal hours.

    Handles: 16 | "16" | "3 ساعات 30 دقيقة" | "ساعتين" | "نصف ساعة"
             | "١٢ ساعة" | "1 day 6 hours" | "45 دقيقة"
    Returns None if nothing parseable (never guesses).
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)

    s = normalize_ar(value) or ""
    if not s:
        return None

    # bare number -> already hours (the sheet's column header says hours)
    if re.fullmatch(r"\d+(?:[.,]\d+)?", s):
        return float(s.replace(",", "."))

    s = s.replace("نصف", "0.5").replace("ثلث", "0.333").replace("ربع", "0.25")

    total = 0.0
    found = False

    # dual forms carry the number inside the word
    if re.search(r"\bساعتين\b|\bساعتان\b", s):
        total += 2.0
        found = True
    if re.search(r"\bدقيقتين\b", s):
        total += 2 / 60
        found = True
    if re.search(r"\bيومين\b", s):
        total += 48.0
        found = True

    for pattern, factor in (
        (rf"(\d+(?:\.\d+)?)\s*{_DAY_WORDS}\b", 24.0),
        (rf"(\d+(?:\.\d+)?)\s*{_HOUR_WORDS}\b", 1.0),
        (rf"(\d+(?:\.\d+)?)\s*{_MIN_WORDS}\b", 1 / 60),
    ):
        for m in re.finditer(pattern, s):
            total += float(m.group(1)) * factor
            found = True

    return round(total, 3) if found else None


# ---------------------------------------------------------------------------
# 3. Controlled vocabularies
# ---------------------------------------------------------------------------

DECISION_MAP = {
    "ادانه": ("CONVICTED", "إدانة", "Convicted"),
    "ادانة": ("CONVICTED", "إدانة", "Convicted"),
    "عدم ادانه": ("NOT_CONVICTED", "عدم إدانة", "Not convicted"),
    "عدم ادانة": ("NOT_CONVICTED", "عدم إدانة", "Not convicted"),
    "قيد الدراسه": ("UNDER_REVIEW", "قيد الدراسة", "Under review"),
}

KINSHIP_MAP = {
    "اسره واحده": ("SINGLE_FAMILY", "أسرة واحدة", "Single family"),
    "اسر مختلفه": ("MULTIPLE_FAMILIES", "أسر مختلفة", "Multiple families"),
    "غير معروف": ("UNKNOWN", "غير معروف", "Unknown"),
}


def _lookup(mapping: dict, key: Optional[str], fallback_code: str):
    if key is None:
        return (fallback_code, None, None)
    return mapping.get(normalize_ar(key), (fallback_code, key, key))


# ---------------------------------------------------------------------------
# 4. Advisory epidemiology: incubation -> likely agent class
#    (standard CDC/WHO foodborne-illness incubation windows — ADVISORY ONLY,
#     never presented to the committee as a finding)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AgentWindow:
    lo: float
    hi: float
    code: str
    ar: str
    en: str


AGENT_WINDOWS = (
    AgentWindow(0.0, 1.0, "CHEMICAL_SCOMBROID",
                "كيميائي / هيستامين (سكومبرويد)", "Chemical / histamine (scombroid)"),
    AgentWindow(1.0, 7.0, "PREFORMED_TOXIN",
                "سموم جاهزة: المكورات العنقودية / العصوية الشمعية",
                "Preformed toxin: S. aureus / B. cereus (emetic)"),
    AgentWindow(7.0, 16.0, "CLOSTRIDIUM_BCEREUS",
                "المطثية الحاطمة / العصوية الشمعية (إسهالي)",
                "C. perfringens / B. cereus (diarrhoeal)"),
    AgentWindow(16.0, 72.0, "INVASIVE_BACTERIAL_VIRAL",
                "سالمونيلا / شيغيلا / نوروفيروس / كامبيلوباكتر",
                "Salmonella / Shigella / Norovirus / Campylobacter"),
    AgentWindow(72.0, float("inf"), "LONG_LATENCY",
                "ليستيريا / التهاب كبد A / طفيليات",
                "Listeria / Hepatitis A / parasitic"),
)


def infer_agent_class(hours: Optional[float]):
    if hours is None:
        return ("UNKNOWN", None, None)
    for w in AGENT_WINDOWS:
        if w.lo <= hours < w.hi:
            return (w.code, w.ar, w.en)
    return ("UNKNOWN", None, None)


# ---------------------------------------------------------------------------
# 5. Advisory attribution rule engine
#    !!! CALIBRATE THESE THRESHOLDS AGAINST THE ACTUAL دليل الوزارة !!!
#    Defaults below reproduce the pattern in the 2026 register; they are a
#    starting hypothesis, not the ministry's published criteria.
# ---------------------------------------------------------------------------

ATTRIBUTION_RULES = {
    "min_incubation_hours": 6.0,   # below this, a single-source outbreak is unlikely
    "min_cases": 3,
    "require_multiple_families": True,
}


def attribution_advisory(hours: Optional[float], cases: Optional[int], kinship_code: str):
    """Return (flag, reason_ar, reason_en). Advisory only — never a verdict."""
    r = ATTRIBUTION_RULES
    reasons_ar, reasons_en = [], []

    if hours is not None and hours < r["min_incubation_hours"]:
        reasons_ar.append(f"فترة حضانة قصيرة ({hours:g} ساعة)")
        reasons_en.append(f"short incubation ({hours:g} h)")
    if cases is not None and cases < r["min_cases"]:
        reasons_ar.append(f"عدد مصابين محدود ({cases})")
        reasons_en.append(f"few cases ({cases})")
    if r["require_multiple_families"] and kinship_code == "SINGLE_FAMILY":
        reasons_ar.append("جميع المصابين من أسرة واحدة")
        reasons_en.append("all cases within one household")

    if not reasons_ar:
        return ("LIKELY_ATTRIBUTABLE",
                "فترة حضانة وعدد مصابين وانتشار عبر أسر متعددة يدعم الإسناد للمنشأة",
                "Incubation, case count and spread across households support attribution")
    return ("UNLIKELY_ATTRIBUTABLE", "؛ ".join(reasons_ar), "; ".join(reasons_en))


# ---------------------------------------------------------------------------
# 6. Workbook -> tidy DataFrame
# ---------------------------------------------------------------------------

COLUMN_MAP = {
    "م": "row_no",
    "التاريخ": "incident_date",
    "اسم المحل": "establishment_name_ar",
    "اسم البلدية": "municipality_ar",
    "رقم الرخصة": "license_no",
    "فترة الحضانة بالساعة": "incubation_raw",
    "عدد المصابين": "cases_count",
    "صلة القرابة": "kinship_raw",
    "قرار اللجنة": "decision_raw",
    "سبب عدم الإدانة طبقا لدليل الوزارة": "non_conviction_reason_ar",
}


def load_poisoning_frame(path, sheet=0, resolver=None) -> pd.DataFrame:
    raw = pd.read_excel(path, sheet_name=sheet)
    raw.columns = [normalize_ar(c) for c in raw.columns]

    norm_map = {normalize_ar(k): v for k, v in COLUMN_MAP.items()}
    missing = [ar for ar, en in norm_map.items() if ar not in raw.columns]
    if missing:
        raise ValueError(f"Missing expected columns in {path}: {missing}")

    df = raw.rename(columns=norm_map)[list(COLUMN_MAP.values())].copy()
    df = df.dropna(how="all").reset_index(drop=True)

    df["incident_date"] = pd.to_datetime(df["incident_date"], errors="coerce").dt.date
    df["license_no"] = (
        df["license_no"].astype("string")
        .str.replace(r"\.0$", "", regex=True).str.strip()
    )
    df["cases_count"] = pd.to_numeric(df["cases_count"], errors="coerce").astype("Int64")

    df["establishment_name"] = df["establishment_name_ar"].map(display_ar)
    df["establishment_key"] = df["establishment_name_ar"].map(normalize_ar)
    df["municipality"] = df["municipality_ar"].map(display_ar)
    df["municipality_key"] = df["municipality_ar"].map(normalize_ar)

    df["incubation_hours"] = df["incubation_raw"].map(parse_incubation_hours)
    df["incubation_raw"] = df["incubation_raw"].map(
        lambda v: None if v is None or pd.isna(v) else str(v)
    )

    df[["decision_code", "decision_ar", "decision_en"]] = pd.DataFrame(
        df["decision_raw"].map(lambda v: _lookup(DECISION_MAP, v, "UNKNOWN")).tolist(),
        index=df.index,
    )
    df[["kinship_code", "kinship_ar", "kinship_en"]] = pd.DataFrame(
        df["kinship_raw"].map(lambda v: _lookup(KINSHIP_MAP, v, "UNKNOWN")).tolist(),
        index=df.index,
    )
    df[["agent_class_code", "agent_class_ar", "agent_class_en"]] = pd.DataFrame(
        df["incubation_hours"].map(infer_agent_class).tolist(), index=df.index
    )
    df[["attribution_flag", "attribution_reason_ar", "attribution_reason_en"]] = pd.DataFrame(
        [
            attribution_advisory(h, (None if pd.isna(c) else int(c)), k)
            for h, c, k in zip(df["incubation_hours"], df["cases_count"], df["kinship_code"])
        ],
        index=df.index,
    )

    df["decision_matches_advisory"] = (
        (df["decision_code"] == "CONVICTED")
        & (df["attribution_flag"] == "LIKELY_ATTRIBUTABLE")
    ) | (
        (df["decision_code"] == "NOT_CONVICTED")
        & (df["attribution_flag"] == "UNLIKELY_ATTRIBUTABLE")
    )

    df["incident_id"] = [
        f"PSN-{d.year if d is not None and not pd.isna(d) else 'NA'}-{i+1:04d}"
        for i, d in enumerate(df["incident_date"])
    ]

    return df[
        [
            "incident_id", "row_no", "incident_date",
            "establishment_name", "establishment_key", "license_no",
            "municipality", "municipality_key",
            "incubation_raw", "incubation_hours",
            "cases_count",
            "kinship_code", "kinship_ar", "kinship_en",
            "decision_code", "decision_ar", "decision_en",
            "non_conviction_reason_ar",
            "agent_class_code", "agent_class_ar", "agent_class_en",
            "attribution_flag", "attribution_reason_ar", "attribution_reason_en",
            "decision_matches_advisory",
        ]
    ]


# ---------------------------------------------------------------------------
# 7. DuckDB loader
# ---------------------------------------------------------------------------

DDL = """
CREATE TABLE IF NOT EXISTS poisoning_incidents (
    incident_id              VARCHAR PRIMARY KEY,
    row_no                   INTEGER,
    incident_date            DATE,
    establishment_name       VARCHAR,
    establishment_key        VARCHAR,
    license_no               VARCHAR,
    municipality             VARCHAR,
    municipality_key         VARCHAR,
    incubation_raw           VARCHAR,
    incubation_hours         DOUBLE,
    cases_count              INTEGER,
    kinship_code             VARCHAR,
    kinship_ar               VARCHAR,
    kinship_en               VARCHAR,
    decision_code            VARCHAR,
    decision_ar              VARCHAR,
    decision_en              VARCHAR,
    non_conviction_reason_ar VARCHAR,
    agent_class_code         VARCHAR,
    agent_class_ar           VARCHAR,
    agent_class_en           VARCHAR,
    attribution_flag         VARCHAR,
    attribution_reason_ar    VARCHAR,
    attribution_reason_en    VARCHAR,
    decision_matches_advisory BOOLEAN
);
"""


def ingest_poisoning_workbook(path, con, sheet=0, replace=True, resolver=None) -> int:

    """Load one workbook into DuckDB. Returns the row count ingested."""
    df = load_poisoning_frame(path, sheet, resolver=resolver)
    con.execute(DDL)
    if replace:
        con.execute(
            "DELETE FROM poisoning_incidents WHERE incident_id IN "
            "(SELECT incident_id FROM df)"
        )
    con.execute("INSERT INTO poisoning_incidents SELECT * FROM df")
    con.execute(open(Path(__file__).with_name("kpis.sql")).read())
    return len(df)


if __name__ == "__main__":
    import sys
    import duckdb

    src = sys.argv[1]
    con = duckdb.connect(sys.argv[2] if len(sys.argv) > 2 else ":memory:")
    n = ingest_poisoning_workbook(src, con)
    print(f"ingested {n} incidents\n")
    con.sql("SELECT * FROM v_poisoning_kpi_headline").show()
    con.sql(
        "SELECT incident_id, incident_date, municipality, incubation_hours, "
        "cases_count, decision_en, attribution_flag, agent_class_en "
        "FROM poisoning_incidents ORDER BY incident_date"
    ).show(max_width=200)