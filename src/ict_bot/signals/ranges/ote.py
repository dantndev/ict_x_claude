"""Optimal Trade Entry — Fibonacci 0.618 / 0.705 / 0.79 zone (concept 11 §1.3)."""

from __future__ import annotations

from dataclasses import dataclass

from ict_bot.signals.base import Direction, Interval, Leg, OTEZone


@dataclass(frozen=True, slots=True)
class OTEConfig:
    low_level: float = 0.618
    high_level: float = 0.79
    sweet_spot: float = 0.705


def ote_zone(leg: Leg, *, config: OTEConfig | None = None) -> OTEZone:
    cfg = config or OTEConfig()
    lo, hi = leg.range.low, leg.range.high
    rng = hi - lo
    if leg.direction == Direction.BULL:
        # Retracement DOWN from the leg's high
        zone_high = hi - cfg.low_level * rng
        zone_low = hi - cfg.high_level * rng
        sweet = hi - cfg.sweet_spot * rng
    else:
        # Retracement UP from the leg's low
        zone_low = lo + cfg.low_level * rng
        zone_high = lo + cfg.high_level * rng
        sweet = lo + cfg.sweet_spot * rng
    return OTEZone(
        direction=leg.direction,
        leg_range=leg.range,
        zone=Interval(low=min(zone_low, zone_high), high=max(zone_low, zone_high)),
        sweet_spot=sweet,
    )
