"""Tests for liquidity pools, equal-extremes clustering, sweeps (concept 10)."""

from __future__ import annotations

from ict_bot.signals.base import Side
from ict_bot.signals.liquidity.pools import (
    PoolConfig,
    cluster_equal_extremes,
    pools_from_swings,
)
from ict_bot.signals.liquidity.sweep import SweepConfig, detect_sweeps_and_consumptions
from ict_bot.structure.swings import detect_swings


def _bars_with_swings(make_bars_fn):
    """Sequence designed to produce one strict SH and one strict SL.

    bar 0: high 101         (warm-up)
    bar 1: high 110  ← SH   (strictly above neighbors)
    bar 2: high 108         (lower)
    bar 3: low 90    ← SL   (strictly below neighbors)
    bar 4: high 96
    """
    return make_bars_fn(
        [
            (100, 101, 99, 100),
            (100, 110, 99, 109),
            (109, 108, 100, 101),   # NOTE: high < bar 1.high → enables strict SH at 1
            (100, 102, 90, 91),     # SL trough
            (91, 96, 93, 95),
        ],
    )


def test_pools_from_swings(make_bars_fn):
    bars = _bars_with_swings(make_bars_fn)
    swings = detect_swings(bars, n=1)
    pools = pools_from_swings(swings, tf="1m")
    sides = {p.side for p in pools}
    assert Side.BSL in sides
    assert Side.SSL in sides


def test_equal_extremes_clustering(make_bars_fn):
    # Two strict SHs at 110 and 110.25 (within 2-tick tolerance on NQ 0.25)
    bars = make_bars_fn(
        [
            (100, 101, 99, 100),
            (100, 110, 99, 109),    # SH-1 peak 110
            (109, 108, 100, 101),
            (101, 105, 100, 104),
            (104, 110.25, 104, 109),  # SH-2 peak 110.25
            (109, 108, 105, 106),
        ],
    )
    swings = detect_swings(bars, n=1)
    cfg = PoolConfig(tolerance_ticks=2, tick_size=0.25, min_cluster_size=2)
    clusters = cluster_equal_extremes(swings, config=cfg)
    bsl_clusters = [c for c in clusters if c.side == Side.BSL]
    assert len(bsl_clusters) == 1
    assert bsl_clusters[0].price == 110.25


def test_sweep_wick_only(make_bars_fn):
    # SH at bar 1 (high 110). Bar 5 wicks to 111 with body close 109 → SWEEP.
    bars = make_bars_fn(
        [
            (100, 101, 99, 100),
            (100, 110, 99, 109),   # SH=110 (confirmed at bar 2)
            (109, 108, 100, 101),
            (101, 105, 100, 104),
            (104, 109, 103, 108),
            (108, 111, 107, 109),  # bar 5: wick > 110, body 109 ≤ 110 → SWEEP
        ],
    )
    swings = detect_swings(bars, n=1)
    pools = pools_from_swings(swings)
    cfg = SweepConfig(min_depth_ticks=1, tick_size=0.25)
    sweeps, consumptions = detect_sweeps_and_consumptions(bars, pools, config=cfg)
    assert any(s.side == Side.BSL and s.index == 5 for s in sweeps)
    assert all(c.index != 5 for c in consumptions)


def test_consumption_when_body_closes_past(make_bars_fn):
    bars = make_bars_fn(
        [
            (100, 101, 99, 100),
            (100, 110, 99, 109),
            (109, 108, 100, 101),
            (101, 105, 100, 104),
            (104, 109, 103, 108),
            (108, 115, 107, 114),  # bar 5: wick > 110 AND body 114 above → CONSUMPTION
        ],
    )
    swings = detect_swings(bars, n=1)
    pools = pools_from_swings(swings)
    _, consumptions = detect_sweeps_and_consumptions(bars, pools)
    assert any(c.index == 5 for c in consumptions)
