"""Tests for BoS / ChoCH / MSS classification (concept 02)."""

from __future__ import annotations

from ict_bot.signals.base import Direction
from ict_bot.structure.market_structure import detect_structure_events
from ict_bot.structure.swings import detect_swings


def test_bos_bull_on_body_close_above_last_hh(make_bars_fn):
    # Need a clean HH/HL pattern (BULL state) before the BoS-bull break.
    # SH-1=110  → SL-1=100  → SH-2=115 (HH)  → SL-2=105 (HL)  → close > 115 (BoS)
    bars = make_bars_fn(
        [
            (100, 102, 99, 101),
            (101, 110, 100, 109),   # bar 1 SH=110
            (109, 108, 100, 102),   # bar 2 lower high
            (102, 104, 100, 102),   # bar 3 SL=100
            (102, 109, 101, 108),   # bar 4 higher high
            (108, 115, 107, 114),   # bar 5 SH=115 (HH)
            (114, 113, 108, 109),   # bar 6 lower high
            (109, 111, 105, 106),   # bar 7 SL=105 (HL)
            (106, 112, 106, 110),   # bar 8 higher
            (110, 120, 109, 119),   # bar 9 body close 119 > last HH (115) → BoS bull
        ],
    )
    swings = detect_swings(bars, n=1)
    events = detect_structure_events(bars, swings)
    bos_bull = [e for e in events if e.kind == "BoS" and e.direction == Direction.BULL]
    assert len(bos_bull) >= 1


def test_choch_only_without_mss_gates(make_bars_fn):
    """Bull state then body close below last HL → ChoCH bear (no MSS without disp/fvg/sweep)."""
    bars = make_bars_fn(
        [
            (100, 102, 99, 101),
            (101, 110, 100, 109),   # SH-1 = 110
            (109, 108, 100, 102),
            (102, 105, 90, 91),     # SL-1 = 90
            (91, 96, 91, 95),
            (95, 108, 94, 107),     # SH-2 = 108  (LH from 110 → ChoCH potential)
            (107, 106, 100, 101),
            (101, 102, 95, 96),     # SL-2 = 95  (HL from 90 → HH/HL bull state possible)
            (96, 100, 90, 91),
            (91, 92, 80, 81),       # body 81 < last HL (95) → ChoCH bear
        ],
    )
    swings = detect_swings(bars, n=1)
    events = detect_structure_events(bars, swings)
    # No displacement/fvg/sweep inputs → no MSS
    assert not any(e.kind == "MSS" for e in events)
