"""Midnight Open: open of the 00:00 NY bar; used as the global bias filter
(longs below, shorts above)."""

from __future__ import annotations

from datetime import date, time

from ict_bot.data.models import Bars
from ict_bot.utils.tz import to_ny


def midnight_open_for(bars: Bars, day: date) -> float | None:
    """Return the open of the 00:00 NY bar for `day`, if present."""
    if bars.empty:
        return None
    df = bars.df
    matches = df.filter(
        df["ts_ny"].dt.replace_time_zone(None).dt.date() == day,
    )
    if matches.is_empty():
        return None
    # First bar of that NY date with time == 00:00
    for row in matches.iter_rows(named=True):
        ts_ny = to_ny(row["ts_ny"])
        if ts_ny.time() == time(0, 0):
            return float(row["open"])
    return None


def midnight_open_filter_long(price: float, mid_open: float | None) -> bool:
    """True iff a long entry is allowed at `price` given the Midnight Open."""
    return mid_open is None or price < mid_open


def midnight_open_filter_short(price: float, mid_open: float | None) -> bool:
    return mid_open is None or price > mid_open
