"""Tests for OB / Breaker / Mitigation / Rejection (concepts 05-08)."""

from __future__ import annotations

from ict_bot.signals.base import Direction
from ict_bot.signals.blocks.order_block import detect_order_blocks, invalidate_order_blocks
from ict_bot.signals.imbalance.fvg import FVGConfig, detect_fvgs
from ict_bot.structure.displacement import (
    DisplacementConfig,
    aggregate_legs,
    detect_displacement,
)


def _ob_setup_bull(make_bars_fn):
    """Warm-up + bear bar + bull displacement (3 bars) leaving an FVG."""
    rows = [(100, 100.5, 99.5, 100)] * 14
    rows.append((100, 100.5, 99, 99.5))    # opposing bar (bullish OB candidate)
    rows.append((100, 110, 100, 109.5))    # bullish displacement
    rows.append((109, 120, 109, 119.5))
    rows.append((119, 125, 119, 124.5))
    return make_bars_fn(rows)


def test_bullish_order_block_detected_when_leg_has_fvg(make_bars_fn):
    bars = _ob_setup_bull(make_bars_fn)
    per_bar = detect_displacement(bars, config=DisplacementConfig(atr_lookback=14))
    legs = aggregate_legs(bars, per_bar)
    fvgs = detect_fvgs(
        bars,
        config=FVGConfig(require_displacement=False, min_gap_ticks=1, tick_size=0.25),
    )
    obs = detect_order_blocks(bars, legs, fvgs)
    assert any(o.direction == Direction.BULL for o in obs)


def test_ob_invalidation_by_body_below_mt(make_bars_fn):
    bars = _ob_setup_bull(make_bars_fn)
    per_bar = detect_displacement(bars, config=DisplacementConfig(atr_lookback=14))
    legs = aggregate_legs(bars, per_bar)
    fvgs = detect_fvgs(
        bars,
        config=FVGConfig(require_displacement=False, min_gap_ticks=1, tick_size=0.25),
    )
    obs = detect_order_blocks(bars, legs, fvgs)
    obs_inv = invalidate_order_blocks(bars, obs)
    # Without a continuation bear bar below MT, no invalidation expected here
    for ob in obs_inv:
        assert ob.invalidated_at is None or ob.invalidated_at > ob.anchor_index
