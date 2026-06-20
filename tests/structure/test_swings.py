"""Tests pinning the swing-detection math (concept 01)."""

from __future__ import annotations

from ict_bot.structure.swings import detect_swings


def test_swing_high_3bar_minimal(make_bars_fn):
    # bars: low, peak, low → swing HIGH at index 1
    bars = make_bars_fn([(100, 101, 99, 100), (101, 110, 100, 109), (108, 109, 100, 101)])
    swings = detect_swings(bars, n=1)
    assert len(swings) == 1
    s = swings[0]
    assert s.index == 1
    assert s.kind == "HIGH"
    assert s.price == 110
    assert s.confirmed_at_index == 2


def test_swing_low_3bar_minimal(make_bars_fn):
    bars = make_bars_fn([(100, 102, 99, 100), (100, 101, 90, 91), (92, 96, 92, 95)])
    swings = detect_swings(bars, n=1)
    assert len(swings) == 1
    s = swings[0]
    assert s.kind == "LOW"
    assert s.price == 90


def test_equal_highs_not_a_swing_strict(make_bars_fn):
    # middle bar's high equals neighbor's high → strict mode rejects
    bars = make_bars_fn([(100, 110, 99, 100), (100, 110, 99, 100), (100, 105, 99, 100)])
    swings = detect_swings(bars, n=1)
    assert all(s.kind != "HIGH" for s in swings)


def test_swing_n2_requires_wider_window(make_bars_fn):
    # peak at index 2 dominates 4 neighbors
    bars = make_bars_fn(
        [
            (100, 102, 99, 101),
            (101, 103, 100, 102),
            (102, 110, 101, 109),
            (109, 108, 102, 103),
            (103, 105, 100, 102),
        ],
    )
    swings_n1 = detect_swings(bars, n=1)
    swings_n2 = detect_swings(bars, n=2)
    assert any(s.index == 2 and s.kind == "HIGH" for s in swings_n1)
    assert any(s.index == 2 and s.kind == "HIGH" for s in swings_n2)


def test_no_swings_on_too_few_bars(make_bars_fn):
    bars = make_bars_fn([(100, 101, 99, 100)])
    assert detect_swings(bars, n=1) == []


def test_unconfirmed_swings_not_emitted(make_bars_fn):
    # 4 bars, peak at index 3 — for n=1 there is no bar 4, so no swing.
    bars = make_bars_fn(
        [(100, 101, 99, 100), (100, 102, 99, 101), (101, 103, 100, 102), (102, 110, 100, 109)],
    )
    swings = detect_swings(bars, n=1)
    assert all(s.index != 3 for s in swings)
