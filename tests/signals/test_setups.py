"""Tests for setup composition: Unicorn, MSS+FVG, OB+OTE, Silver Bullet, PO3."""

from __future__ import annotations

from datetime import datetime

from ict_bot.signals.base import (
    FVG,
    Breaker,
    Direction,
    Interval,
    Leg,
    LiquidityPool,
    OrderBlock,
    Side,
    StructureEvent,
    Sweep,
    Swing,
)
from ict_bot.signals.setups.po3 import (
    PO3Phase,
    evaluate_po3,
    po3_entry_allowed,
)
from ict_bot.signals.setups.unicorn import UnicornConfig, detect_unicorns
from ict_bot.utils.tz import NY


def _bars_simple(make_bars_fn):
    return make_bars_fn(
        [
            (100, 105, 100, 104),
            (104, 110, 103, 109),
            (109, 115, 108, 114),
            (114, 120, 113, 119),
            (119, 125, 118, 124),
        ],
    )


def test_unicorn_signal_with_intersection(make_bars_fn):
    bars = _bars_simple(make_bars_fn)
    leg = Leg(direction=Direction.BULL, start_index=1, end_index=4,
              range=Interval(low=103, high=125))
    ob = OrderBlock(
        direction=Direction.BULL,
        anchor_index=0,
        range=Interval(low=100, high=105),
        leg_ref=leg,
        invalidated_at=4,
    )
    # Breaker direction = BULL (it's a long entry zone). origin OB invalidated at 4.
    breaker = Breaker(
        direction=Direction.BULL,
        range=Interval(low=110, high=114),
        origin_ob=ob,
        sweep_index=1,
        invalidator_index=3,
    )
    fvg = FVG(
        direction=Direction.BULL,
        anchor_index=2,
        ts_ny=datetime(2026, 6, 1, 9, 3, tzinfo=NY),
        range=Interval(low=112, high=114),
    )
    swing = Swing(index=4, ts_ny=datetime(2026, 6, 1, 9, 4, tzinfo=NY),
                  kind="HIGH", price=130, confirmed_at_index=5)
    target_pool = LiquidityPool(
        side=Side.BSL, price=130, anchor_swings=(swing,),
        created_at_index=5, is_cluster=False, tf="1m",
    )
    cfg = UnicornConfig(require_inside_ote=False, min_rr=1.0, sl_offset_ticks=4)
    signals = detect_unicorns(bars, [breaker], [fvg], [target_pool], config=cfg)
    assert len(signals) == 1
    s = signals[0]
    assert s.setup_name == "unicorn"
    assert s.direction == Direction.BULL
    assert s.take_profit == 130
    assert s.rr > 1.0


def test_po3_distribution_after_judas(make_bars_fn):
    bars = _bars_simple(make_bars_fn)
    swing = Swing(index=0, ts_ny=datetime(2026, 6, 1, 9, 0, tzinfo=NY),
                  kind="LOW", price=100, confirmed_at_index=1)
    pool = LiquidityPool(side=Side.SSL, price=100, anchor_swings=(swing,),
                         created_at_index=1, is_cluster=False, tf="1m")
    judas = Sweep(side=Side.SSL, index=1,
                  ts_ny=datetime(2026, 6, 1, 9, 1, tzinfo=NY),
                  pool=pool, depth=0.5)
    mss = StructureEvent(kind="MSS", direction=Direction.BULL,
                         index=2, ts_ny=datetime(2026, 6, 1, 9, 2, tzinfo=NY),
                         broken_price=110)
    snap = evaluate_po3(bars, 0, 4, Direction.BULL, [judas], [mss])
    assert snap.phase == PO3Phase.DISTRIBUTION
    assert snap.judas_index == 1
    assert snap.distribution_start_index == 2
    # entry allowed only below mid_open for BULL bias
    assert po3_entry_allowed(snap, price=110, direction=Direction.BULL, mid_open=115) is True
    assert po3_entry_allowed(snap, price=120, direction=Direction.BULL, mid_open=115) is False


def test_po3_disabled_when_bias_none(make_bars_fn):
    bars = _bars_simple(make_bars_fn)
    snap = evaluate_po3(bars, 0, 4, None, [], [])
    assert snap.phase == PO3Phase.DISABLED
