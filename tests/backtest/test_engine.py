"""Tests for the event-driven backtest engine (Phase 5)."""

from __future__ import annotations

from datetime import datetime, timedelta

import polars as pl

from ict_bot.backtest.engine import BacktestConfig, run_backtest
from ict_bot.data.models import Bars
from ict_bot.risk.limits import LimitsConfig
from ict_bot.risk.sizing import InstrumentSpec, RiskConfig
from ict_bot.signals.base import Direction
from ict_bot.signals.setups.base import Signal, TradeSide
from ict_bot.utils.tz import NY


def _bars_for_engine(start_hour: int = 9) -> Bars:
    """30 bars starting at the given NY hour. Trending up."""
    base = datetime(2026, 6, 1, start_hour, 0)
    rows = []
    price = 100.0
    for i in range(30):
        rows.append(
            {
                "ts_ny": base + timedelta(minutes=i),
                "open": price,
                "high": price + 1.0,
                "low": price - 1.0,
                "close": price + 0.5,
                "volume": 10,
            }
        )
        price += 0.5
    df = pl.DataFrame(rows).with_columns(pl.col("ts_ny").dt.replace_time_zone(NY.key))
    return Bars(df=df, tf="1m", symbol="TEST")


def test_tp_hit_produces_winning_trade():
    bars = _bars_for_engine(start_hour=9)
    # Signal at bar 2 (ts 09:02), BUY entry at 101, SL=100, TP=104.
    # Fill at bar 3 open. Bar 3 open=101.5. TP=104 → reached by bar 6 (price ~103.5+1=104.5).
    s = Signal(
        setup_name="test",
        side=TradeSide.BUY,
        direction=Direction.BULL,
        entry_price=101.0,
        stop_loss=100.0,
        take_profit=104.0,
        ts_ny=bars.df["ts_ny"][2],
        bar_index=2,
    )
    cfg = BacktestConfig(
        starting_equity=100_000.0,
        enforce_killzones=False,
        enforce_midnight_filter=False,
        slippage_ticks=0,
        commission_per_side_usd=0.0,
    )
    result = run_backtest(
        bars, [s], config=cfg,
        instrument=InstrumentSpec(),
        risk=RiskConfig(per_trade_risk_pct=0.5, min_quantity=1, max_quantity=1),
        limits=LimitsConfig(max_trades_per_day=10),
    )
    assert len(result.portfolio.trades) == 1
    t = result.portfolio.trades[0]
    assert t.pnl_usd > 0
    assert t.r_multiple > 0


def test_sl_hit_produces_losing_trade():
    bars = _bars_for_engine(start_hour=9)
    # SELL at 101 with SL=102, TP=98. Trend is UP → SL will hit.
    s = Signal(
        setup_name="test",
        side=TradeSide.SELL,
        direction=Direction.BEAR,
        entry_price=101.0,
        stop_loss=102.0,
        take_profit=98.0,
        ts_ny=bars.df["ts_ny"][2],
        bar_index=2,
    )
    cfg = BacktestConfig(
        enforce_killzones=False,
        enforce_midnight_filter=False,
        slippage_ticks=0,
        commission_per_side_usd=0.0,
    )
    result = run_backtest(
        bars, [s], config=cfg,
        risk=RiskConfig(per_trade_risk_pct=0.5, min_quantity=1, max_quantity=1),
    )
    assert len(result.portfolio.trades) == 1
    assert result.portfolio.trades[0].pnl_usd < 0


def test_killzone_gating_skips_outside_window():
    # Start at 06:00 NY → outside all killzones → engine should skip the signal.
    bars = _bars_for_engine(start_hour=6)
    s = Signal(
        setup_name="test",
        side=TradeSide.BUY,
        direction=Direction.BULL,
        entry_price=101.0,
        stop_loss=100.0,
        take_profit=104.0,
        ts_ny=bars.df["ts_ny"][2],
        bar_index=2,
    )
    cfg = BacktestConfig(enforce_killzones=True, enforce_midnight_filter=False)
    result = run_backtest(bars, [s], config=cfg)
    assert len(result.portfolio.trades) == 0
    assert result.skipped_signals >= 1
    assert "outside_gate" in result.reasons_skipped
