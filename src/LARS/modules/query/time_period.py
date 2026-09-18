"""
time_period.py — extracted from core_query_engine.py (2026-09-18, Phase 3 split).

Arabic/English time-period parsing: relative periods
(آخر 3 أشهر / last N weeks), dual forms, absolute Arabic months,
and the anchor-date range label.
Methods are byte-identical to their pre-split versions; this module only
relocates them. TimePeriodMixin is mixed into CoreQueryEngine — methods refer to
engine state (self._get_connection(), detection helpers, handlers) via self.
"""
import re
import logging
from typing import Optional, Tuple

import pandas as pd

# ══════════════════════════════════════════════════════════════════════════════
# Time-period detection helpers (module-level constants)
# ══════════════════════════════════════════════════════════════════════════════
_ARABIC_DIGITS = str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789')

_PERIOD_UNIT_MAP = {
    'يوم': 'day', 'ايام': 'day', 'أيام': 'day', 'day': 'day', 'days': 'day',
    'اسبوع': 'week', 'اسابيع': 'week', 'أسابيع': 'week', 'week': 'week', 'weeks': 'week',
    'شهر': 'month', 'شهور': 'month', 'اشهر': 'month', 'أشهر': 'month', 'month': 'month', 'months': 'month',
    'سنة': 'year', 'سنوات': 'year', 'عام': 'year', 'أعوام': 'year', 'year': 'year', 'years': 'year',
}
_ARABIC_NUMBER_WORDS = {
    'ثلاثة': '3', 'ثلاث': '3',
    'أربعة': '4', 'اربعة': '4', 'أربع': '4', 'اربع': '4',
    'خمسة': '5', 'خمس': '5',
    'ستة': '6', 'ست': '6',
    'سبعة': '7', 'سبع': '7',
    'ثمانية': '8', 'ثمان': '8',
    'تسعة': '9', 'تسع': '9',
    'عشرة': '10', 'عشر': '10',
}
_ARABIC_MONTHS = {
    'يناير': 1, 'فبراير': 2, 'مارس': 3, 'أبريل': 4, 'ابريل': 4,
    'مايو': 5, 'يونيو': 6, 'يوليو': 7, 'أغسطس': 8, 'اغسطس': 8,
    'سبتمبر': 9, 'أكتوبر': 10, 'اكتوبر': 10, 'نوفمبر': 11, 'ديسمبر': 12,
}
        
_DUAL_FORMS = {
    'يومين': ('day', 2),
    'اسبوعين': ('week', 2),
    'أسبوعين': ('week', 2),
    'شهرين': ('month', 2),
    'سنتين': ('year', 2),
    'عامين': ('year', 2),
}


class TimePeriodMixin:
    def _parse_time_period(self, query: str) -> Optional[Tuple[int, str]]:
        """
        Parse time period from a query, returning (n, unit) or None.
        Unit is one of: 'day', 'week', 'month', 'year'.
        """
        if not query:
            return None
        # Convert spelled-out Arabic numbers ("ثلاثة أشهر") to digits ("3 أشهر")
        # BEFORE the digit regex runs below — otherwise "آخر ثلاثة أشهر" never
        # matches because \d+ only sees literal digits, not number words, and
        # falls through silently to "no date filter" (i.e. the ENTIRE dataset).
        for word, digit in _ARABIC_NUMBER_WORDS.items():
            query = re.sub(rf'\b{word}\b', digit, query)
        q = query.translate(_ARABIC_DIGITS)
        q_lower = q.lower()

        # 1. Dual forms
        for dual_word, (unit, n) in _DUAL_FORMS.items():
            if dual_word in q:
                return n, unit

        # 2. Numeric / implicit "last" patterns
        m = re.search(
            r'(?:اخر|آخر|last)\s*(\d+)?\s*'
            r'(يوم(?!ين)|ايام|أيام|اسبوع(?!ين)|اسابيع|أسابيع|شهر(?!ين)|شهور|اشهر|أشهر|سنة|سنوات|عام(?!ين)|أعوام'
            r'|day|days|week|weeks|month|months|year|years)',
            q_lower
        )
        if m:
            n = int(m.group(1)) if m.group(1) else 1
            unit = _PERIOD_UNIT_MAP.get(m.group(2))
            if unit and n > 0:
                return n, unit

        # 3. Fixed phrases
        if any(p in q for p in ['الشهر الماضي', 'الشهر الفائت']):
            return 1, 'month'
        if any(p in q for p in ['السنة الماضية', 'العام الماضي']):
            return 1, 'year'
        if any(p in q for p in ['الاسبوع الماضي', 'الأسبوع الماضي']):
            return 1, 'week'
        if any(p in q for p in ['امس', 'أمس']):
            return 1, 'day'

        return None

    def _detect_time_period(self, query: str) -> Optional[str]:
        parsed = self._parse_time_period(query)
        if parsed is None:
            return None
        n, unit = parsed
        anchor = '(SELECT MAX(strptime("التاريخ", \'%d/%m/%Y\')) FROM chemistry_tidy)'
        return f'AND strptime("التاريخ", \'%d/%m/%Y\') >= ({anchor} - INTERVAL {n} {unit})'

    def _detect_absolute_month(self, query: str) -> Optional[str]:
        """
        Detect an absolute Arabic month name (e.g. 'مارس') and return a SQL
        date filter fragment for that calendar month, regardless of year —
        safe because the dataset spans a single year (confirmed: Jan-May
        2026 in current data). If the dataset later spans multiple years,
        this will need a year-disambiguation step added.
        """
        for month_name, month_num in _ARABIC_MONTHS.items():
            if month_name in query:
                return f'AND date_part(\'month\', strptime("التاريخ", \'%d/%m/%Y\')) = {month_num}'
        return None

    def _get_anchor_date(self):
        """Latest sample date actually present in chemistry_tidy — the same
        anchor used by _detect_time_period()'s SQL filter, fetched once so
        we can also render a human-readable date range in responses."""
        try:
            con = self._get_connection()
            row = con.execute(
                'SELECT MAX(strptime("التاريخ", \'%d/%m/%Y\')) AS anchor FROM chemistry_tidy'
            ).fetchone()
            con.close()
            return row[0] if row and row[0] is not None else None
        except Exception as exc:
            logging.warning(f"Anchor date fetch failed: {exc}")
            return None

    def _period_label(self, query: str) -> Optional[str]:
        parsed = self._parse_time_period(query)
        if parsed is None:
            return None
        n, unit = parsed

        anchor = self._get_anchor_date()
        if anchor is None:
            return None

        from dateutil.relativedelta import relativedelta
        if unit == 'day':
            start = anchor - pd.Timedelta(days=n)
        elif unit == 'week':
            start = anchor - pd.Timedelta(weeks=n)
        elif unit == 'month':
            start = anchor - relativedelta(months=n)
        else:  # year
            start = anchor - relativedelta(years=n)

        return f"من {start.strftime('%d/%m/%Y')} إلى {anchor.strftime('%d/%m/%Y')}"
