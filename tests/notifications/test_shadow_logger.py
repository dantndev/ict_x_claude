"""Tests for the shadow signal logger."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from ict_bot.notifications.shadow_logger import ShadowSignalLogger
from ict_bot.signals.base import Direction
from ict_bot.signals.setups.base import Signal, TradeSide
from ict_bot.utils.tz import NY


def _make_signal(hour: int, minute: int) -> Signal:
    return Signal(
        setup_name="test",
        side=TradeSide.BUY,
        direction=Direction.BULL,
        entry_price=20000.0,
        stop_loss=19990.0,
        take_profit=20015.0,
        ts_ny=datetime(2026, 6, 22, hour, minute, tzinfo=NY),
        bar_index=0,
    )


def test_shadow_logger_writes_header_and_row(tmp_path: Path):
    log = ShadowSignalLogger(out_dir=tmp_path)
    sig = _make_signal(10, 15)  # silver_bullet_am
    log.record(sig, executed=True, skip_reason="", notes="ticket=abc")
    log.close()

    csv_path = tmp_path / "2026-06-22.csv"
    assert csv_path.exists()
    rows = list(csv.reader(csv_path.open(encoding="utf-8")))
    assert rows[0][0] == "ts_ny"
    assert rows[1][1] == "test"           # setup name
    assert rows[1][7] == "silver_bullet_am"
    assert rows[1][8] == "1"               # in_mode_A
    assert rows[1][9] == "1"               # in_mode_B
    assert rows[1][10] == "1"              # in_mode_C
    assert rows[1][11] == "1"              # executed


def test_shadow_logger_tags_modes_correctly(tmp_path: Path):
    log = ShadowSignalLogger(out_dir=tmp_path)
    # 03:00 NY = London KZ → in_A only
    log.record(_make_signal(3, 0), executed=False, skip_reason="outside_window")
    # 09:00 NY = NY AM KZ → in_A + in_C, not in_B
    log.record(_make_signal(9, 0), executed=False, skip_reason="outside_window")
    log.close()
    rows = list(csv.reader((tmp_path / "2026-06-22.csv").open(encoding="utf-8")))
    london_row = rows[1]
    ny_am_row = rows[2]
    assert london_row[7] == "london_kz"
    assert (london_row[8], london_row[9], london_row[10]) == ("1", "0", "0")
    assert ny_am_row[7] == "ny_am_kz"
    assert (ny_am_row[8], ny_am_row[9], ny_am_row[10]) == ("1", "0", "1")


def test_shadow_logger_rolls_over_by_day(tmp_path: Path):
    log = ShadowSignalLogger(out_dir=tmp_path)
    log.record(_make_signal(10, 15), executed=True)
    # Different date
    sig2 = Signal(
        setup_name="t",
        side=TradeSide.SELL,
        direction=Direction.BEAR,
        entry_price=20000.0, stop_loss=20010.0, take_profit=19985.0,
        ts_ny=datetime(2026, 6, 23, 14, 30, tzinfo=NY),
        bar_index=0,
    )
    log.record(sig2, executed=False, skip_reason="paused")
    log.close()
    assert (tmp_path / "2026-06-22.csv").exists()
    assert (tmp_path / "2026-06-23.csv").exists()
