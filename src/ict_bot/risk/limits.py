"""Trade-gating limits applied by the backtest engine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class LimitsConfig:
    daily_loss_limit_pct: float = 2.0        # of starting-of-day equity
    max_trades_per_day: int = 6
    max_consecutive_losses: int = 4


@dataclass(slots=True)
class LimitsState:
    starting_equity_today: float = 0.0
    current_day: date | None = None
    trades_today: int = 0
    consecutive_losses: int = 0
    cumulative_loss_today_usd: float = 0.0
    locked_for_day: bool = False
    locked_for_streak: bool = False

    def reset_for_day(self, today: date, equity: float) -> None:
        self.starting_equity_today = equity
        self.current_day = today
        self.trades_today = 0
        self.cumulative_loss_today_usd = 0.0
        self.locked_for_day = False

    def register_trade(self, pnl_usd: float, *, config: LimitsConfig) -> None:
        self.trades_today += 1
        if pnl_usd < 0:
            self.cumulative_loss_today_usd += -pnl_usd
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0
        loss_cap = self.starting_equity_today * config.daily_loss_limit_pct / 100.0
        if self.cumulative_loss_today_usd >= loss_cap:
            self.locked_for_day = True
        if self.consecutive_losses >= config.max_consecutive_losses:
            self.locked_for_streak = True

    def can_trade(self, *, config: LimitsConfig) -> bool:
        if self.locked_for_day or self.locked_for_streak:
            return False
        return self.trades_today < config.max_trades_per_day
