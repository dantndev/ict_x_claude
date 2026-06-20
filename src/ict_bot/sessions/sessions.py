"""Convenience aggregate for sessions: convenience re-exports + session window iter."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime

from ict_bot.sessions.killzones import (
    SessionsConfig,
    force_flat,
    kz_active,
    lunch,
    new_entries_allowed,
    news_block,
    silver_bullet_am,
    silver_bullet_pm,
)


@dataclass(frozen=True, slots=True)
class SessionTag:
    name: str
    start: datetime
    end: datetime


def session_tag_at(dt: datetime, cfg: SessionsConfig | None = None) -> str:  # noqa: PLR0911
    """Return a single-string label for the current session window at `dt`."""
    cfg = cfg or SessionsConfig()
    if news_block(dt, cfg):
        return "news_block"
    if force_flat(dt, cfg):
        return "force_flat"
    if lunch(dt, cfg):
        return "ny_lunch"
    if silver_bullet_am(dt, cfg):
        return "silver_bullet_am"
    if silver_bullet_pm(dt, cfg):
        return "silver_bullet_pm"
    if kz_active(dt, cfg):
        t = dt.timetz().replace(tzinfo=None)  # used only for window discrimination
        ll, lu = cfg.london_kz
        if ll <= t <= lu:
            return "london_kz"
        am_l, am_u = cfg.ny_am_kz
        if am_l <= t <= am_u:
            return "ny_am_kz"
        pm_l, pm_u = cfg.ny_pm_kz
        if pm_l <= t <= pm_u:
            return "ny_pm_kz"
    return "idle"


def iter_session_windows(
    bars_ts_list: list[datetime], cfg: SessionsConfig | None = None,
) -> Iterator[tuple[datetime, str]]:
    """Yield `(ts, session_tag)` for each bar timestamp."""
    cfg = cfg or SessionsConfig()
    for ts in bars_ts_list:
        yield ts, session_tag_at(ts, cfg)


__all__ = [
    "SessionTag",
    "SessionsConfig",
    "force_flat",
    "iter_session_windows",
    "kz_active",
    "lunch",
    "new_entries_allowed",
    "news_block",
    "session_tag_at",
    "silver_bullet_am",
    "silver_bullet_pm",
]
