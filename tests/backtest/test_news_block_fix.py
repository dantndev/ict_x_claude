"""Regression test for the news_block fill leak (pilot 004 finding).

A signal detected at 08:29 NY (still inside NY AM KZ) but filled on the
next bar at 08:30 NY (news_block window) used to slip through. The fill
gate now re-checks new_entries_allowed.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import polars as pl

from ict_bot.backtest.engine import BacktestConfig, run_backtest
from ict_bot.data.models import Bars
from ict_bot.risk.limits import LimitsConfig
from ict_bot.risk.sizing import InstrumentSpec, RiskConfig
from ict_bot.sessions.killzones import SessionsConfig
from ict_bot.signals.base import Direction
from ict_bot.signals.setups.base import Signal, TradeSide
from ict_bot.utils.tz import NY


def _bars_around_news_block() -> Bars:
    base = datetime(2026, 6, 22, 8, 25)  # Monday 08:25 NY
    rows = []
    price = 20000.0
    for i in range(20):
        rows.append({
            "ts_ny": base + timedelta(minutes=i),
            "open": price, "high": price + 2, "low": price - 2,
            "close": price + 1, "volume": 100,
        })
        price += 1
    df = pl.DataFrame(rows).with_columns(pl.col("ts_ny").dt.replace_time_zone(NY.key))
    return Bars(df=df, tf="1m", symbol="TEST")


def test_signal_at_829_does_not_fill_at_830_news_block():
    bars = _bars_around_news_block()
    # Signal at bar index 4 (08:29 NY), would fill at bar 5 (08:30 = news_block).
    signal = Signal(
        setup_name="test",
        side=TradeSide.BUY,
        direction=Direction.BULL,
        entry_price=20004.0,
        stop_loss=20000.0,
        take_profit=20012.0,
        ts_ny=bars.df["ts_ny"][4],
        bar_index=4,
    )
    cfg = BacktestConfig(
        enforce_killzones=True,
        enforce_midnight_filter=False,
        slippage_ticks=0,
        commission_per_side_usd=0.0,
    )
    result = run_backtest(
        bars, [signal], config=cfg,
        instrument=InstrumentSpec(),
        risk=RiskConfig(),
        limits=LimitsConfig(),
        sessions=SessionsConfig(),
    )
    # Signal was submitted at 08:29 (passes detection-time gate), but fill
    # would land at 08:30 (news_block). The new fill-time gate must block it.
    assert len(result.portfolio.trades) == 0
    assert result.reasons_skipped.get("fill_gate_blocked", 0) >= 1
