"""Tests for risk sizing + limits state machine."""

from __future__ import annotations

from datetime import date

from ict_bot.risk.limits import LimitsConfig, LimitsState
from ict_bot.risk.sizing import InstrumentSpec, RiskConfig, size_position


def test_size_position_basic_nq():
    spec = InstrumentSpec(tick_size=0.25, tick_value_usd=5.0, point_value_usd=20.0)
    cfg = RiskConfig(per_trade_risk_pct=0.5, min_quantity=1, max_quantity=10)
    qty = size_position(
        equity_usd=100_000.0,
        entry_price=20000.0,
        stop_loss=19990.0,    # 10 pts = 40 ticks = $200 / contract risk
        instrument=spec,
        risk=cfg,
    )
    # Target risk = $500; per-contract = $200 → 500//200 = 2
    assert qty == 2


def test_size_position_zero_when_sl_too_wide():
    spec = InstrumentSpec()
    cfg = RiskConfig(per_trade_risk_pct=0.1, max_quantity=10)
    qty = size_position(
        equity_usd=10_000.0,
        entry_price=20000.0,
        stop_loss=19000.0,    # 1000 pts = $20k/contract — way over $10 target
        instrument=spec,
        risk=cfg,
    )
    assert qty == 0


def test_size_position_zero_when_sl_eq_entry():
    qty = size_position(100_000, 20000, 20000)
    assert qty == 0


def test_limits_resets_per_day():
    state = LimitsState()
    cfg = LimitsConfig(daily_loss_limit_pct=2.0, max_trades_per_day=3,
                       max_consecutive_losses=4)
    state.reset_for_day(date(2026, 6, 1), 100_000.0)
    assert state.can_trade(config=cfg) is True
    state.register_trade(-500.0, config=cfg)
    state.register_trade(-500.0, config=cfg)
    state.register_trade(-500.0, config=cfg)
    # 3 trades today → can_trade False (max reached)
    assert state.can_trade(config=cfg) is False


def test_limits_daily_loss_lock():
    state = LimitsState()
    cfg = LimitsConfig(daily_loss_limit_pct=1.0, max_trades_per_day=10,
                       max_consecutive_losses=10)
    state.reset_for_day(date(2026, 6, 1), 10_000.0)
    state.register_trade(-150.0, config=cfg)   # $150 loss > 1% of $10k = $100
    assert state.locked_for_day is True
    assert state.can_trade(config=cfg) is False


def test_limits_streak_lock():
    state = LimitsState()
    cfg = LimitsConfig(daily_loss_limit_pct=10.0, max_trades_per_day=10,
                       max_consecutive_losses=2)
    state.reset_for_day(date(2026, 6, 1), 100_000.0)
    state.register_trade(-50.0, config=cfg)
    state.register_trade(-50.0, config=cfg)
    assert state.locked_for_streak is True


def test_limits_streak_lock_resets_next_day():
    """A new trading day must clear the streak lock. Previously a streak
    halt persisted forever; pilot 003 exposed the bug."""
    state = LimitsState()
    cfg = LimitsConfig(daily_loss_limit_pct=10.0, max_trades_per_day=10,
                       max_consecutive_losses=2)
    state.reset_for_day(date(2026, 6, 1), 100_000.0)
    state.register_trade(-50.0, config=cfg)
    state.register_trade(-50.0, config=cfg)
    assert state.locked_for_streak is True
    assert not state.can_trade(config=cfg)

    state.reset_for_day(date(2026, 6, 2), 99_900.0)
    assert state.locked_for_streak is False
    assert state.consecutive_losses == 0
    assert state.can_trade(config=cfg)
