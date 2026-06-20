"""Data validation: gap detection, duplicate detection, timezone sanity.

These functions never mutate the input; they return reports and raise only
when an invariant is so broken that downstream code cannot proceed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from itertools import pairwise
from typing import Final

import polars as pl

from ict_bot.data.models import TF_MINUTES, Bars, Ticks, Timeframe

CME_BREAK_HOUR: Final[int] = 17  # 17:00 NY — start of the daily CME maintenance break


@dataclass(frozen=True, slots=True)
class GapReport:
    timeframe: Timeframe
    gaps: list[tuple[datetime, datetime, int]] = field(default_factory=list)
    """(prev_ts, next_ts, missing_bar_count)"""

    @property
    def total_missing(self) -> int:
        return sum(g[2] for g in self.gaps)


@dataclass(frozen=True, slots=True)
class DuplicateReport:
    count: int
    timestamps: list[datetime] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class TimezoneReport:
    has_tz: bool
    tz_name: str | None
    expected: str = "America/New_York"

    @property
    def ok(self) -> bool:
        return self.has_tz and self.tz_name == self.expected


# ──────────────────────── Bars validators ────────────────────────


def check_bar_gaps(bars: Bars, *, session_filter: bool = False) -> GapReport:
    """Detect missing bars assuming a regular `tf` cadence.

    If `session_filter=True`, gaps that span well-known non-trading windows
    (e.g., CME daily break 17:00-18:00 NY) are NOT counted as missing.
    For Phase-2 simplicity, V1 only filters the 17:00-18:00 break window.
    """
    if bars.empty:
        return GapReport(timeframe=bars.tf)
    step = timedelta(minutes=TF_MINUTES[bars.tf])
    ts = bars.df.get_column("ts_ny").to_list()
    gaps: list[tuple[datetime, datetime, int]] = []
    for prev, nxt in pairwise(ts):
        delta = nxt - prev
        if delta <= step:
            continue
        missing = int(delta / step) - 1
        if missing <= 0:
            continue
        if session_filter and _spans_break(prev, nxt):
            continue
        gaps.append((prev, nxt, missing))
    return GapReport(timeframe=bars.tf, gaps=gaps)


def _spans_break(prev: datetime, nxt: datetime) -> bool:
    """Return True iff the gap [prev, nxt] crosses the CME 17:00-18:00 NY break.

    Naive but safe for the only well-known CME break window relevant in V1.
    """
    crosses_break_intraday = prev.time().hour < CME_BREAK_HOUR <= nxt.time().hour
    crosses_break_overday = (
        prev.date() != nxt.date() and prev.time().hour >= CME_BREAK_HOUR
    )
    return crosses_break_intraday or crosses_break_overday


def check_bar_duplicates(bars: Bars) -> DuplicateReport:
    if bars.empty:
        return DuplicateReport(count=0)
    dup_ts = (
        bars.df
        .group_by("ts_ny")
        .len()
        .filter(pl.col("len") > 1)
        .get_column("ts_ny")
        .to_list()
    )
    return DuplicateReport(count=len(dup_ts), timestamps=dup_ts)


def check_bar_timezone(bars: Bars) -> TimezoneReport:
    schema = bars.df.schema
    dtype = schema.get("ts_ny")
    if dtype is None:
        return TimezoneReport(has_tz=False, tz_name=None)
    tz = getattr(dtype, "time_zone", None)
    return TimezoneReport(has_tz=tz is not None, tz_name=tz)


# ──────────────────────── Ticks validators ────────────────────────


def check_tick_monotonicity(ticks: Ticks) -> bool:
    """Return True iff ts_ny is monotonically non-decreasing."""
    if ticks.empty:
        return True
    arr = ticks.df.get_column("ts_ny")
    return bool((arr.diff().fill_null(timedelta(0)) >= timedelta(0)).all())
