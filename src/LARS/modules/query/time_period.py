"""
time_period.py — extracted from core_query_engine.py (2026-09-18, Phase 3 split).

Arabic/English time-period parsing: relative periods
(آخر 3 أشهر / last N weeks), dual forms, absolute Arabic months,
and the anchor-date range label.
Methods are byte-identical to their pre-split versions; this module only
relocates them. TimePeriodMixin is mixed into CoreQueryEngine — methods refer to
engine state (self._get_connection(), detection helpers, handlers) via self.
"""
import logging
from typing import Optional, Tuple

import pandas as pd

from modules.query.text_norm import norm, parse_period

# ══════════════════════════════════════════════════════════════════════════════
# Time-period detection helpers (module-level constants)
# ══════════════════════════════════════════════════════════════════════════════

_ARABIC_MONTHS = {
    'يناير': 1, 'فبراير': 2, 'مارس': 3, 'أبريل': 4, 'ابريل': 4,
    'مايو': 5, 'يونيو': 6, 'يوليو': 7, 'أغسطس': 8, 'اغسطس': 8,
    'سبتمبر': 9, 'أكتوبر': 10, 'اكتوبر': 10, 'نوفمبر': 11, 'ديسمبر': 12,
}
        


class TimePeriodMixin:
    def _parse_time_period(self, query: str) -> Optional[Tuple[int, str]]:
        """
        Parse a relative period from a query, returning (n, unit) or None.
        Unit is one of: 'day', 'week', 'month', 'year'.

        Delegates to text_norm.parse_period, shared normalization included, so
        "آخر ٣ شهور", "آخر ثلاث شهور", "الأشهر الثلاثة الأخيرة", "الشهر
        الماضي", "خلال الشهرين الماضيين" and "last 3 months" all parse.
        """
        if not query:
            return None
        return parse_period(query)

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
        q = norm(query)
        for month_name, month_num in _ARABIC_MONTHS.items():
            if norm(month_name) in q:
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
