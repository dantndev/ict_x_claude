"""Displacement detection (concept 03).

A bar is a displacement bar when its body dominates its range, its body exceeds
a multiple of recent ATR, and its wick on the close side is short. Runs of
displacement bars in the same direction (with a small allowed gap) collapse
into Legs.
"""

from __future__ import annotations

from dataclasses import dataclass

from ict_bot.data.models import Bars
from ict_bot.signals.base import Direction, Interval, Leg


@dataclass(frozen=True, slots=True)
class DisplacementConfig:
    atr_lookback: int = 14
    body_range_min: float = 0.6
    body_atr_min: float = 1.5
    wick_to_body_max: float = 0.35
    leg_gap_max_bars: int = 1


def wilder_atr(bars: Bars, n: int) -> list[float]:
    """Compute Wilder ATR over `n` bars. Returns one value per bar.

    First `n` entries are zero (insufficient history) — caller should not rely
    on them for thresholding.
    """
    if bars.empty:
        return []
    highs = bars.df.get_column("high").to_list()
    lows = bars.df.get_column("low").to_list()
    closes = bars.df.get_column("close").to_list()
    m = len(highs)
    tr: list[float] = [0.0] * m
    for i in range(m):
        if i == 0:
            tr[i] = highs[i] - lows[i]
            continue
        tr[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
    atr: list[float] = [0.0] * m
    if m < n:
        return atr
    # Seed with simple average of first n true ranges
    atr[n - 1] = sum(tr[0:n]) / n
    for i in range(n, m):
        atr[i] = (atr[i - 1] * (n - 1) + tr[i]) / n
    return atr


def detect_displacement(
    bars: Bars, *, config: DisplacementConfig | None = None,
) -> list[Direction | None]:
    """Return a per-bar list of {Direction.BULL, Direction.BEAR, None}."""
    cfg = config or DisplacementConfig()
    if bars.empty:
        return []
    opens = bars.df.get_column("open").to_list()
    highs = bars.df.get_column("high").to_list()
    lows = bars.df.get_column("low").to_list()
    closes = bars.df.get_column("close").to_list()
    m = len(opens)
    atr = wilder_atr(bars, cfg.atr_lookback)
    out: list[Direction | None] = [None] * m
    for t in range(cfg.atr_lookback, m):
        body = abs(closes[t] - opens[t])
        rng = highs[t] - lows[t]
        if rng <= 0 or body <= 0 or atr[t] <= 0:
            continue
        if body / rng < cfg.body_range_min:
            continue
        if body < cfg.body_atr_min * atr[t]:
            continue
        if closes[t] > opens[t]:
            top_wick = highs[t] - closes[t]
            if top_wick > cfg.wick_to_body_max * body:
                continue
            out[t] = Direction.BULL
        elif closes[t] < opens[t]:
            bot_wick = closes[t] - lows[t]
            if bot_wick > cfg.wick_to_body_max * body:
                continue
            out[t] = Direction.BEAR
    return out


def aggregate_legs(
    bars: Bars,
    per_bar: list[Direction | None],
    *,
    gap_max: int = 1,
) -> list[Leg]:
    """Collapse a per-bar displacement series into maximal contiguous legs.

    A leg is broken by an opposing-direction displacement bar, or by more than
    `gap_max` consecutive non-displacement bars.
    """
    if bars.empty or not per_bar:
        return []
    highs = bars.df.get_column("high").to_list()
    lows = bars.df.get_column("low").to_list()
    legs: list[Leg] = []
    m = len(per_bar)
    i = 0
    while i < m:
        d = per_bar[i]
        if d is None:
            i += 1
            continue
        end = i
        gap = 0
        j = i + 1
        while j < m:
            dj = per_bar[j]
            if dj == d:
                end = j
                gap = 0
            elif dj is None:
                gap += 1
                if gap > gap_max:
                    break
            else:  # opposite direction
                break
            j += 1
        leg_low = min(lows[i : end + 1])
        leg_high = max(highs[i : end + 1])
        legs.append(
            Leg(
                direction=d,
                start_index=i,
                end_index=end,
                range=Interval(low=leg_low, high=leg_high),
            ),
        )
        i = end + 1
    return legs
