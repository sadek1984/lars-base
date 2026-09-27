"""
QuerySpec: the only thing the LLM produces.

Filter values are the words as the user wrote them; the validator (Phase 2)
resolves them against the Catalog. The schema is flat (no unions) so it can
be passed as a structured-output schema.
"""
from __future__ import annotations

from datetime import date, timedelta
from enum import Enum
from typing import List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Metric(str, Enum):
    sample_count = "sample_count"
    noncompliant_count = "noncompliant_count"            # sample_result: the official verdict
    noncompliance_rate = "noncompliance_rate"
    above_limit_sample_count = "above_limit_sample_count"  # technical: above the EU MRL
    above_limit_rate = "above_limit_rate"
    top_pesticides = "top_pesticides"
    pesticide_list = "pesticide_list"
    never_detected_list = "never_detected_list"  # detected somewhere in the data, never within the filters


class Scope(str, Enum):
    all = "all"
    non_compliant = "non_compliant"


class GroupBy(str, Enum):
    category = "category"
    product = "product"
    municipality = "municipality"
    neighborhood = "neighborhood"
    month = "month"


class PeriodType(str, Enum):
    none = "none"
    relative = "relative"              # "آخر 3 شهور": n units back from MAX(test_date)
    absolute_month = "absolute_month"  # "في مارس"
    range = "range"                    # "من يناير إلى مارس", inclusive


class PeriodUnit(str, Enum):
    day = "day"
    week = "week"
    month = "month"
    year = "year"


class Sort(str, Enum):
    desc = "desc"
    asc = "asc"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Filters(_Strict):
    category: List[str] = Field(default_factory=list)
    product: List[str] = Field(default_factory=list)
    municipality: List[str] = Field(default_factory=list)
    neighborhood: List[str] = Field(default_factory=list)
    pesticide: List[str] = Field(default_factory=list)


class Period(_Strict):
    type: PeriodType = PeriodType.none
    n: Optional[int] = Field(default=None, ge=1, le=36)
    unit: Optional[PeriodUnit] = None
    month: Optional[int] = Field(default=None, ge=1, le=12)
    year: Optional[int] = Field(default=None, ge=2000, le=2100)
    start: Optional[date] = None
    end: Optional[date] = None

    @model_validator(mode="after")
    def _fields_match_type(self):
        needed = {PeriodType.none: set(), PeriodType.relative: {"n", "unit"},
                  PeriodType.absolute_month: {"month"}, PeriodType.range: {"start", "end"}}[self.type]
        allowed = needed | ({"year"} if self.type is PeriodType.absolute_month else set())
        given = {k for k in ("n", "unit", "month", "year", "start", "end") if getattr(self, k) is not None}
        if needed - given:
            raise ValueError(f"period '{self.type.value}' needs {sorted(needed - given)}")
        if given - allowed:
            raise ValueError(f"period '{self.type.value}' does not take {sorted(given - allowed)}")
        if self.type is PeriodType.range and self.start > self.end:
            raise ValueError("period start is after end")
        return self

    def bounds(self, max_date: date) -> Optional[Tuple[date, date]]:
        """Inclusive [start, end] on test_date. Relative periods are anchored on
        MAX(test_date), not today: 'last 3 months' = test_date >= max - 3 months."""
        if self.type is PeriodType.none:
            return None
        if self.type is PeriodType.range:
            return self.start, self.end
        if self.type is PeriodType.absolute_month:
            year = self.year or max_date.year
            nxt = date(year + (self.month == 12), self.month % 12 + 1, 1)
            return date(year, self.month, 1), nxt - timedelta(days=1)
        return _minus(max_date, self.n, self.unit), max_date


def _minus(d: date, n: int, unit: PeriodUnit) -> date:
    if unit is PeriodUnit.day:
        return d - timedelta(days=n)
    if unit is PeriodUnit.week:
        return d - timedelta(weeks=n)
    months = n * (12 if unit is PeriodUnit.year else 1)
    y, m = divmod(d.year * 12 + d.month - 1 - months, 12)
    m += 1
    last = (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)).day
    return date(y, m, min(d.day, last))   # same clamping as DuckDB's INTERVAL month


class QuerySpec(_Strict):
    metric: Metric
    scope: Scope = Scope.all
    filters: Filters = Field(default_factory=Filters)
    period: Period = Field(default_factory=Period)
    group_by: Optional[GroupBy] = None
    top_n: int = Field(default=5, ge=1, le=50)
    sort: Sort = Sort.desc
    mrl_multiple: Optional[float] = Field(default=None, ge=1, le=1000)  # "أكثر من ضعف الحد": 2
    unsupported: bool = False
    reason: Optional[str] = None

    @model_validator(mode="after")
    def _unsupported_needs_reason(self):
        if self.unsupported and not (self.reason or "").strip():
            raise ValueError("unsupported=true needs a reason")
        if self.mrl_multiple is not None and self.metric not in ABOVE_LIMIT_METRICS:
            raise ValueError("mrl_multiple applies only to above-limit metrics")
        return self


ABOVE_LIMIT_METRICS = {Metric.above_limit_sample_count, Metric.above_limit_rate}
RATE_METRICS = {Metric.noncompliance_rate, Metric.above_limit_rate}
COUNT_METRICS = {Metric.sample_count, Metric.noncompliant_count, Metric.above_limit_sample_count}
ANALYTE_METRICS = {Metric.top_pesticides, Metric.pesticide_list, Metric.never_detected_list}
