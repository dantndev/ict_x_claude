"""Fair Value Gap detection — BISI, SIBI, Consequent Encroachment (concept 04).

A 3-candle pattern where bar t's high and bar t+2's low (BISI) fail to overlap,
leaving an empty price band that the IPDA tends to rebalance. The middle bar
(t+1) is the displacement bar and is optionally required to be a valid
displacement of the matching direction.
"""

from __future__ import annotations

from dataclasses import dataclass

from ict_bot.data.models import Bars
from ict_bot.signals.base import FVG, Direction, Interval


@dataclass(frozen=True, slots=True)
class FVGConfig:
    require_displacement: bool = True
    min_gap_ticks: int = 1
    tick_size: float = 0.25  # NQ default; override per instrument


def detect_fvgs(
    bars: Bars,
    *,
    config: FVGConfig | None = None,
    displacement: list[Direction | None] | None = None,
) -> list[FVG]:
    """Return all FVGs (BISI + SIBI) in `bars`.

    `displacement` is a per-bar direction list (from
    `structure.displacement.detect_displacement`). When provided AND
    `config.require_displacement=True`, the middle bar (t+1) must be a
    displacement in the matching direction.
    """
    cfg = config or FVGConfig()
    if bars.empty:
        return []
    highs = bars.df.get_column("high").to_list()
    lows = bars.df.get_column("low").to_list()
    ts_ny = bars.df.get_column("ts_ny").to_list()
    m = len(highs)
    min_gap = cfg.min_gap_ticks * cfg.tick_size
    out: list[FVG] = []
    for t in range(m - 2):
        # BISI: low of bar t+2 strictly above high of bar t
        if lows[t + 2] - highs[t] >= min_gap:
            if cfg.require_displacement and displacement is not None:
                if displacement[t + 1] != Direction.BULL:
                    pass
                else:
                    out.append(
                        FVG(
                            direction=Direction.BULL,
                            anchor_index=t,
                            ts_ny=ts_ny[t + 1],
                            range=Interval(low=highs[t], high=lows[t + 2]),
                        ),
                    )
            else:
                out.append(
                    FVG(
                        direction=Direction.BULL,
                        anchor_index=t,
                        ts_ny=ts_ny[t + 1],
                        range=Interval(low=highs[t], high=lows[t + 2]),
                    ),
                )
        # SIBI: high of bar t+2 strictly below low of bar t
        if lows[t] - highs[t + 2] >= min_gap:
            if cfg.require_displacement and displacement is not None:
                if displacement[t + 1] != Direction.BEAR:
                    pass
                else:
                    out.append(
                        FVG(
                            direction=Direction.BEAR,
                            anchor_index=t,
                            ts_ny=ts_ny[t + 1],
                            range=Interval(low=highs[t + 2], high=lows[t]),
                        ),
                    )
            else:
                out.append(
                    FVG(
                        direction=Direction.BEAR,
                        anchor_index=t,
                        ts_ny=ts_ny[t + 1],
                        range=Interval(low=highs[t + 2], high=lows[t]),
                    ),
                )
    return out


def invalidate_fvgs(bars: Bars, fvgs: list[FVG]) -> list[FVG]:
    """Walk forward and set `invalidated_at` on FVGs whose CE is body-closed beyond.

    For BISI: body close below CE invalidates.
    For SIBI: body close above CE invalidates.
    """
    if not fvgs or bars.empty:
        return fvgs
    opens = bars.df.get_column("open").to_list()
    closes = bars.df.get_column("close").to_list()
    m = len(opens)
    result: list[FVG] = []
    for g in fvgs:
        inv_at: int | None = g.invalidated_at
        if inv_at is None:
            start = g.anchor_index + 3  # first bar after the 3-bar pattern
            for s in range(start, m):
                body_top = max(opens[s], closes[s])
                body_bot = min(opens[s], closes[s])
                if g.direction == Direction.BULL and body_bot < g.ce:
                    inv_at = s
                    break
                if g.direction == Direction.BEAR and body_top > g.ce:
                    inv_at = s
                    break
        result.append(
            FVG(
                direction=g.direction,
                anchor_index=g.anchor_index,
                ts_ny=g.ts_ny,
                range=g.range,
                invalidated_at=inv_at,
            ),
        )
    return result
