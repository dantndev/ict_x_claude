"""Timezone helpers.

The whole bot runs on America/New_York. This module centralizes the conversion
and normalization so that no other module ever calls `pytz` or `zoneinfo` directly.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Final
from zoneinfo import ZoneInfo

NY: Final[ZoneInfo] = ZoneInfo("America/New_York")
UTC: Final[ZoneInfo] = ZoneInfo("UTC")


def to_ny(dt: datetime) -> datetime:
    """Return `dt` localized to America/New_York.

    Naive datetimes are assumed to be UTC (consistent with most exchange feeds).
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(NY)


def to_utc(dt: datetime) -> datetime:
    """Return `dt` converted to UTC. Naive datetimes are assumed NY-local."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=NY)
    return dt.astimezone(UTC)


def ny_time(dt: datetime) -> time:
    """Return the time-of-day portion of `dt` on the NY clock."""
    return to_ny(dt).time()


def ny_date(dt: datetime) -> date:
    """Return the calendar date of `dt` on the NY clock."""
    return to_ny(dt).date()


def is_between(t: time, start: time, end: time, *, inclusive_end: bool = True) -> bool:
    """Half-open / closed interval check that handles wrap-around (e.g., 20:00-00:00)."""
    if start <= end:
        return (start <= t <= end) if inclusive_end else (start <= t < end)
    return (t >= start) or ((t <= end) if inclusive_end else (t < end))


def midnight_ny(d: date) -> datetime:
    """Return the NY midnight datetime for a given calendar date."""
    return datetime.combine(d, time(0, 0), tzinfo=NY)


def add_bars(dt: datetime, n: int, tf_minutes: int) -> datetime:
    """Add `n` bars of length `tf_minutes` to a datetime (timezone-preserving)."""
    return dt + timedelta(minutes=n * tf_minutes)
