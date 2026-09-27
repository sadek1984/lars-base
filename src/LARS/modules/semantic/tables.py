"""
The two reviewed lookup tables under src/LARS/config/.

category_map.csv  Arabic/English category word -> stored "نوع العينة" values.
analyte_map.csv   raw pesticide_name -> canonical analyte (misspellings,
                  case and glued values merged; mycotoxins counted with
                  pesticides; non-analyte rows such as 'NO CBD' map to '').

The CSVs are the source of truth; edit them, not code.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from modules.query.text_norm import norm

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"
CATEGORY_MAP_CSV = CONFIG_DIR / "category_map.csv"
ANALYTE_MAP_CSV = CONFIG_DIR / "analyte_map.csv"


def _strip_article(term: str) -> str:
    """'الخضروات' and 'خضروات' are one entry: drop a leading ال per word."""
    return " ".join(w[2:] if w.startswith("ال") and len(w) > 3 else w for w in norm(term).split())


def category_key(term: str) -> str:
    return _strip_article(term)


def load_category_map(path: Path = CATEGORY_MAP_CSV) -> Dict[str, Tuple[str, ...]]:
    """normalized term -> stored category values (sorted)."""
    out: Dict[str, Tuple[str, ...]] = {}
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            values = tuple(sorted(v.strip() for v in row["categories"].split("|") if v.strip()))
            key = category_key(row["term"])
            if key in out and out[key] != values:
                raise ValueError(f"category_map.csv: '{row['term']}' mapped twice with different values")
            out[key] = values
    return out


@dataclass(frozen=True)
class AnalyteMap:
    raw_to_canonical: Dict[str, str]     # every raw pesticide_name; '' = not an analyte
    canonical_class: Dict[str, str]      # canonical -> 'pesticide' | 'mycotoxin'

    def raw_names(self, canonical: str) -> List[str]:
        """Every stored spelling of a canonical analyte, sorted (SQL IN list)."""
        return sorted(r for r, c in self.raw_to_canonical.items() if c == canonical)

    @property
    def canonical_names(self) -> List[str]:
        return sorted(self.canonical_class)


def load_analyte_map(path: Path = ANALYTE_MAP_CSV) -> AnalyteMap:
    raw_to_canonical: Dict[str, str] = {}
    canonical_class: Dict[str, str] = {}
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            raw, can, cls = row["raw_name"], row["canonical_name"].strip(), row["analyte_class"].strip()
            if raw in raw_to_canonical:
                raise ValueError(f"analyte_map.csv: '{raw}' listed twice")
            raw_to_canonical[raw] = can
            if can:
                if canonical_class.setdefault(can, cls) != cls:
                    raise ValueError(f"analyte_map.csv: '{can}' has two classes")
    return AnalyteMap(raw_to_canonical, canonical_class)
