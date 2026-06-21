"""Killzones / news block / lunch / force-flatten in America/New_York (concept 13)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time

from ict_bot.utils.tz import to_ny


@dataclass(frozen=True, slots=True)
class SessionsConfig:
    london_kz: tuple[time, time] = (time(2, 0), time(5, 0))
    ny_am_kz: tuple[time, time] = (time(7, 0), time(10, 0))
    ny_pm_kz: tuple[time, time] = (time(13, 30), time(16, 0))
    news_block: tuple[time, time] = (time(8, 30), time(8, 35))
    lunch: tuple[time, time] = (time(12, 0), time(13, 0))
    force_flat_at: time = time(16, 30)
    silver_bullet_am: tuple[time, time] = (time(10, 0), time(11, 0))
    silver_bullet_pm: tuple[time, time] = (time(14, 0), time(15, 0))
    # Mode-based filter. When set, new_entries_allowed only fires inside the
    # listed windows. Valid tags:
    #   "london_kz", "ny_am_kz", "ny_pm_kz",
    #   "silver_bullet_am", "silver_bullet_pm"
    # None = all killzones + silver-bullet windows are allowed (default).
    allowed_windows: tuple[str, ...] | None = None


def _in(t: time, window: tuple[time, time], *, inclusive_end: bool = True) -> bool:
    start, end = window
    return (start <= t <= end) if inclusive_end else (start <= t < end)


def now_ny(dt: datetime) -> time:
    return to_ny(dt).time()


def kz_active(dt: datetime, cfg: SessionsConfig | None = None) -> bool:
    cfg = cfg or SessionsConfig()
    t = now_ny(dt)
    return _in(t, cfg.london_kz) or _in(t, cfg.ny_am_kz) or _in(t, cfg.ny_pm_kz)


def news_block(dt: datetime, cfg: SessionsConfig | None = None) -> bool:
    cfg = cfg or SessionsConfig()
    return _in(now_ny(dt), cfg.news_block, inclusive_end=False)


def lunch(dt: datetime, cfg: SessionsConfig | None = None) -> bool:
    cfg = cfg or SessionsConfig()
    return _in(now_ny(dt), cfg.lunch, inclusive_end=False)


def force_flat(dt: datetime, cfg: SessionsConfig | None = None) -> bool:
    cfg = cfg or SessionsConfig()
    return now_ny(dt) == cfg.force_flat_at


def silver_bullet_am(dt: datetime, cfg: SessionsConfig | None = None) -> bool:
    """10:00-11:00 NY. Tag only (per concept 13 §3.3) — does NOT require kz_active."""
    cfg = cfg or SessionsConfig()
    return _in(now_ny(dt), cfg.silver_bullet_am, inclusive_end=False)


def silver_bullet_pm(dt: datetime, cfg: SessionsConfig | None = None) -> bool:
    """14:00-15:00 NY. Tag only."""
    cfg = cfg or SessionsConfig()
    return _in(now_ny(dt), cfg.silver_bullet_pm, inclusive_end=False)


def new_entries_allowed(dt: datetime, cfg: SessionsConfig | None = None) -> bool:
    """Trade gate: inside an allowed window, not in news block, not in lunch.

    When `cfg.allowed_windows` is None (default), any killzone or silver-bullet
    window opens entries. When set, only the listed windows open entries.
    """
    cfg = cfg or SessionsConfig()
    if news_block(dt, cfg) or lunch(dt, cfg):
        return False
    t = now_ny(dt)
    if cfg.allowed_windows is None:
        return (
            _in(t, cfg.london_kz)
            or _in(t, cfg.ny_am_kz)
            or _in(t, cfg.ny_pm_kz)
            or _in(t, cfg.silver_bullet_am, inclusive_end=False)
            or _in(t, cfg.silver_bullet_pm, inclusive_end=False)
        )
    windows = set(cfg.allowed_windows)
    if "london_kz" in windows and _in(t, cfg.london_kz):
        return True
    if "ny_am_kz" in windows and _in(t, cfg.ny_am_kz):
        return True
    if "ny_pm_kz" in windows and _in(t, cfg.ny_pm_kz):
        return True
    if "silver_bullet_am" in windows and _in(t, cfg.silver_bullet_am, inclusive_end=False):
        return True
    if "silver_bullet_pm" in windows and _in(t, cfg.silver_bullet_pm, inclusive_end=False):
        return True
    return False
