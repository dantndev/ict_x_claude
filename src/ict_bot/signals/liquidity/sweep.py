"""Liquidity sweep detection (concept 10 §3.3).

A sweep is a wick beyond a pool followed by a body close NOT past the pool.
A body close past the pool is "consumption" (the pool is taken), not a sweep —
the engine emits both events distinctly.
"""

from __future__ import annotations

from dataclasses import dataclass

from ict_bot.data.models import Bars
from ict_bot.signals.base import LiquidityPool, Side, Sweep


@dataclass(frozen=True, slots=True)
class SweepConfig:
    min_depth_ticks: int = 1
    tick_size: float = 0.25


@dataclass(frozen=True, slots=True)
class PoolConsumption:
    side: Side
    index: int
    pool: LiquidityPool


def detect_sweeps_and_consumptions(
    bars: Bars,
    pools: list[LiquidityPool],
    *,
    config: SweepConfig | None = None,
) -> tuple[list[Sweep], list[PoolConsumption]]:
    """Walk bars forward, classify each interaction with each pool.

    Returns:
        (sweeps, consumptions)
    """
    cfg = config or SweepConfig()
    if bars.empty or not pools:
        return [], []
    opens = bars.df.get_column("open").to_list()
    highs = bars.df.get_column("high").to_list()
    lows = bars.df.get_column("low").to_list()
    closes = bars.df.get_column("close").to_list()
    ts_ny = bars.df.get_column("ts_ny").to_list()
    m = len(opens)
    min_depth = cfg.min_depth_ticks * cfg.tick_size

    sweeps: list[Sweep] = []
    consumptions: list[PoolConsumption] = []

    for p in pools:
        for t in range(p.created_at_index, m):
            body_top = max(opens[t], closes[t])
            body_bot = min(opens[t], closes[t])
            if p.side == Side.BSL:
                wick_over = highs[t] - p.price
                if wick_over < min_depth:
                    continue
                if body_top <= p.price:
                    sweeps.append(
                        Sweep(side=Side.BSL, index=t, ts_ny=ts_ny[t], pool=p, depth=wick_over),
                    )
                else:
                    consumptions.append(PoolConsumption(side=Side.BSL, index=t, pool=p))
                    break  # pool consumed; subsequent interactions belong to new structure
            else:  # SSL
                wick_under = p.price - lows[t]
                if wick_under < min_depth:
                    continue
                if body_bot >= p.price:
                    sweeps.append(
                        Sweep(side=Side.SSL, index=t, ts_ny=ts_ny[t], pool=p, depth=wick_under),
                    )
                else:
                    consumptions.append(PoolConsumption(side=Side.SSL, index=t, pool=p))
                    break
    return sweeps, consumptions
