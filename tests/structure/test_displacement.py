"""Tests for displacement classification + leg aggregation (concept 03)."""

from __future__ import annotations

from ict_bot.signals.base import Direction
from ict_bot.structure.displacement import (
    DisplacementConfig,
    aggregate_legs,
    detect_displacement,
)


def _flat_then_pop(make_bars_fn, *, pop_at: int = 14):
    """14 flat bars (small range), then a strong bullish bar."""
    rows = [(100, 100.5, 99.5, 100)] * pop_at
    rows.append((100, 110, 100, 109.5))  # big body, no top wick
    return make_bars_fn(rows)


def test_strong_bull_bar_classified_as_bull(make_bars_fn):
    bars = _flat_then_pop(make_bars_fn, pop_at=14)
    cfg = DisplacementConfig(atr_lookback=14, body_atr_min=1.5, body_range_min=0.6)
    out = detect_displacement(bars, config=cfg)
    assert out[14] == Direction.BULL


def test_long_top_wick_disqualifies(make_bars_fn):
    # Bullish body but with a big top wick → fail the wick check
    rows = [(100, 100.5, 99.5, 100)] * 14
    rows.append((100, 120, 100, 105))  # huge top wick
    bars = make_bars_fn(rows)
    out = detect_displacement(bars)
    assert out[14] is None


def test_small_body_disqualifies(make_bars_fn):
    rows = [(100, 100.5, 99.5, 100)] * 14
    rows.append((100, 101, 99, 100.1))  # tiny body, large range
    bars = make_bars_fn(rows)
    out = detect_displacement(bars)
    assert out[14] is None


def test_leg_aggregation_three_bull_bars(make_bars_fn):
    # 14 flat warm-up, then 3 bull displacement bars, then 1 flat
    rows = [(100, 100.5, 99.5, 100)] * 14
    rows.append((100, 110, 100, 109.5))
    rows.append((109, 120, 109, 119.5))
    rows.append((119, 130, 119, 129.5))
    rows.append((129, 130, 128, 129))
    bars = make_bars_fn(rows)
    per_bar = detect_displacement(bars)
    legs = aggregate_legs(bars, per_bar, gap_max=1)
    assert len(legs) == 1
    assert legs[0].direction == Direction.BULL
    assert legs[0].start_index == 14
    assert legs[0].end_index == 16
    assert legs[0].range.low == 100
    assert legs[0].range.high == 130


def test_leg_terminated_by_opposing_bar(make_bars_fn):
    rows = [(100, 100.5, 99.5, 100)] * 14
    rows.append((100, 110, 100, 109.5))   # bull
    rows.append((109, 110, 100, 100.5))   # bear (closes far below open)
    bars = make_bars_fn(rows)
    per_bar = detect_displacement(bars)
    legs = aggregate_legs(bars, per_bar, gap_max=1)
    # First bull leg should terminate at the opposing bar
    assert legs[0].direction == Direction.BULL
    assert legs[0].end_index == 14
