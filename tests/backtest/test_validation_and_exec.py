"""Tests for Phase 7 (validation), Phase 8 (ML stub), Phase 9 (execution).

Each test uses small synthetic fixtures to avoid network / large data dependencies.
"""

from __future__ import annotations

from datetime import datetime

import polars as pl
import pytest

from ict_bot.backtest.engine import BacktestConfig, run_backtest
from ict_bot.backtest.orders import PositionStatus, Trade
from ict_bot.backtest.portfolio import Portfolio
from ict_bot.data.models import Bars
from ict_bot.execution.broker import BrokerError
from ict_bot.execution.kill_switch import KillSwitch, KillSwitchTripped
from ict_bot.execution.paper_broker import PaperBroker
from ict_bot.ml.features import FEATURE_KEYS, features_for_signal
from ict_bot.risk.sizing import RiskConfig
from ict_bot.signals.base import Direction
from ict_bot.signals.setups.base import Signal, TradeSide
from ict_bot.utils.tz import NY
from ict_bot.validation.bootstrap import bootstrap_stats

# ───────── Phase 7 — bootstrap ─────────

def _portfolio_with_trades() -> Portfolio:
    pf = Portfolio(starting_equity=100_000.0, equity=100_000.0)
    base = datetime(2026, 6, 1, 9, 0, tzinfo=NY)
    for i in range(30):
        pnl = 100.0 if i < 18 else -80.0
        t = Trade(
            setup_name="test",
            side="BUY",
            entry_price=100.0, exit_price=101.0,
            stop_loss=99.0, take_profit=102.0,
            quantity=1,
            entry_ts_ny=base, exit_ts_ny=base,
            entry_index=i, exit_index=i,
            pnl_usd=pnl, r_multiple=1.0 if pnl > 0 else -1.0,
            status=PositionStatus.CLOSED_TP if pnl > 0 else PositionStatus.CLOSED_SL,
        )
        pf.trades.append(t)
        pf.equity += pnl
    return pf


def test_bootstrap_returns_stats():
    pf = _portfolio_with_trades()
    stats = bootstrap_stats(pf, iterations=200, seed=1)
    assert stats.n_iterations == 200
    assert stats.final_equity_mean > 0
    assert 0.0 <= stats.prob_profitable <= 1.0


# ───────── Phase 8 — ML features ─────────

def test_features_for_signal_returns_expected_keys():
    s = Signal(
        setup_name="unicorn",
        side=TradeSide.BUY,
        direction=Direction.BULL,
        entry_price=20000.0, stop_loss=19990.0, take_profit=20030.0,
        ts_ny=datetime(2026, 6, 1, 9, 30, tzinfo=NY),
        bar_index=20,
    )
    df = pl.DataFrame(
        {
            "ts_ny": [datetime(2026, 6, 1, 9, i, tzinfo=NY) for i in range(50)],
            "open": [20000.0] * 50,
            "high": [20010.0] * 50,
            "low": [19990.0] * 50,
            "close": [20005.0] * 50,
            "volume": [100] * 50,
        },
    )
    bars = Bars(df=df, tf="1m", symbol="TEST")
    f = features_for_signal(s, None, bars)
    for k in FEATURE_KEYS:
        assert k in f
    assert f["setup_unicorn"] == 1.0
    assert f["side_buy"] == 1.0
    assert f["atr14"] == 20.0


# ───────── Phase 9 — execution ─────────

def test_paper_broker_round_trip_profit():
    b = PaperBroker(starting_equity=100_000.0, tick_size=0.25,
                    tick_value_usd=0.50, commission_per_side_usd=0.0,
                    slippage_ticks=0)
    b.connect()
    b.feed_price("MNQM6", 20000.0)
    ack = b.submit_market("MNQM6", "BUY", 1, sl=19990.0, tp=20010.0)
    assert ack.accepted
    # Move price to TP — triggers close
    b.feed_price("MNQM6", 20010.0)
    assert b.equity_usd() > 100_000.0


def test_paper_broker_rejects_when_disconnected():
    b = PaperBroker()
    b.feed_price("X", 100.0)
    with pytest.raises(BrokerError):
        b.submit_market("X", "BUY", 1, sl=99.0, tp=101.0)


def test_kill_switch_blocks_after_trip():
    ks = KillSwitch()
    ks.assert_armed()  # OK while not tripped
    ks.trip("daily loss limit")
    with pytest.raises(KillSwitchTripped):
        ks.assert_armed()
    ks.reset()
    ks.assert_armed()  # OK again


# ───────── Backtest engine smoke (Phase 5 sanity, re-checked) ─────────

def test_backtest_runs_with_empty_signals():
    df = pl.DataFrame(
        {
            "ts_ny": [datetime(2026, 6, 1, 9, i, tzinfo=NY) for i in range(30)],
            "open": [100.0] * 30,
            "high": [101.0] * 30,
            "low": [99.0] * 30,
            "close": [100.5] * 30,
            "volume": [10] * 30,
        },
    )
    bars = Bars(df=df, tf="1m", symbol="TEST")
    result = run_backtest(
        bars, [], config=BacktestConfig(enforce_killzones=False,
                                         enforce_midnight_filter=False),
        risk=RiskConfig(),
    )
    assert result.portfolio.equity == 100_000.0
