"""Tests for dealing range / OTE / PD-array selector (concepts 09 + 11)."""

from __future__ import annotations

from ict_bot.signals.base import (
    Breaker,
    Direction,
    Interval,
    Leg,
    OrderBlock,
    PDArrayKind,
)
from ict_bot.signals.ranges.dealing_range import classify_price, dealing_range_at
from ict_bot.signals.ranges.ote import ote_zone
from ict_bot.signals.selector import (
    build_registry,
    dominant_pd_array_at,
    pd_arrays_at,
)
from ict_bot.structure.swings import detect_swings


def test_dealing_range_premium_discount(make_bars_fn):
    bars = make_bars_fn(
        [
            (100, 102, 99, 101),
            (101, 110, 100, 109),
            (109, 108, 100, 102),
            (102, 105, 90, 91),
            (91, 96, 91, 95),
        ],
    )
    swings = detect_swings(bars, n=1)
    dr = dealing_range_at(swings, at_index=4)
    assert dr is not None
    assert dr.range.low == 90
    assert dr.range.high == 110
    assert dr.equilibrium == 100
    assert classify_price(105, dr) == "PREMIUM"
    assert classify_price(95, dr) == "DISCOUNT"
    assert classify_price(100, dr) == "EQUILIBRIUM"


def test_ote_bull_leg():
    # Leg low=100, high=200; OTE = retracement from 200 down
    leg = Leg(
        direction=Direction.BULL,
        start_index=0, end_index=10,
        range=Interval(low=100, high=200),
    )
    z = ote_zone(leg)
    # zone_low = 200 - 0.79*100 = 121; zone_high = 200 - 0.618*100 = 138.2; sweet = 129.5
    assert abs(z.zone.low - 121) < 1e-6
    assert abs(z.zone.high - 138.2) < 1e-6
    assert abs(z.sweet_spot - 129.5) < 1e-6


def test_selector_breaker_dominates_ob_at_same_price():
    ob = OrderBlock(
        direction=Direction.BULL,
        anchor_index=10,
        range=Interval(low=100, high=110),
        leg_ref=Leg(Direction.BULL, 0, 5, Interval(99, 115)),
        htf_anchored=True,
    )
    breaker = Breaker(
        direction=Direction.BULL,
        range=Interval(low=100, high=110),
        origin_ob=ob,
        sweep_index=12,
        invalidator_index=20,
    )
    registry = build_registry([ob, breaker])
    top = dominant_pd_array_at(105, "BUY", registry)
    assert top is not None
    assert top.kind == PDArrayKind.BREAKER  # rank 2 < rank 6


def test_selector_filters_premium_for_sells():
    ob_premium = OrderBlock(
        direction=Direction.BEAR,
        anchor_index=10,
        range=Interval(low=100, high=110),
        leg_ref=Leg(Direction.BEAR, 0, 5, Interval(95, 115)),
        htf_anchored=True,
    )
    registry = build_registry([ob_premium])
    buys = pd_arrays_at(105, "BUY", registry)
    sells = pd_arrays_at(105, "SELL", registry)
    assert buys == []
    assert len(sells) == 1
