"""Portfolio state: equity, open positions, closed trades, daily equity series."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import polars as pl

from ict_bot.backtest.orders import Position, PositionStatus, Trade


@dataclass(slots=True)
class Portfolio:
    starting_equity: float
    equity: float
    open_positions: dict[int, Position] = field(default_factory=dict)
    trades: list[Trade] = field(default_factory=list)
    equity_series: list[tuple[datetime, float]] = field(default_factory=list)

    def record_equity_point(self, ts_ny: datetime) -> None:
        self.equity_series.append((ts_ny, self.equity))

    def close_position(
        self,
        position_id: int,
        exit_price: float,
        exit_index: int,
        exit_ts_ny: datetime,
        status: PositionStatus,
        *,
        tick_size: float,
        tick_value_usd: float,
        commission_per_side_usd: float = 1.25,
    ) -> Trade:
        pos = self.open_positions.pop(position_id)
        pos.exit_price = exit_price
        pos.exit_index = exit_index
        pos.exit_ts_ny = exit_ts_ny
        pos.status = status
        # PnL: ticks * tick_value * signed quantity
        ticks_moved = (exit_price - pos.fill.fill_price) / tick_size
        gross_usd = ticks_moved * tick_value_usd * pos.quantity
        commission = 2.0 * commission_per_side_usd * abs(pos.quantity)
        pnl = gross_usd - commission
        pos.pnl_usd = pnl
        self.equity += pnl
        # R-multiple
        sl_distance = abs(pos.order.entry_price - pos.order.stop_loss)
        r_value_usd = (sl_distance / tick_size) * tick_value_usd * abs(pos.quantity)
        r_multiple = pnl / r_value_usd if r_value_usd > 0 else 0.0
        trade = Trade(
            setup_name=pos.order.setup_name,
            side=pos.order.side,
            entry_price=pos.fill.fill_price,
            exit_price=exit_price,
            stop_loss=pos.order.stop_loss,
            take_profit=pos.order.take_profit,
            quantity=pos.quantity,
            entry_ts_ny=pos.fill.fill_ts_ny,
            exit_ts_ny=exit_ts_ny,
            entry_index=pos.fill.fill_index,
            exit_index=exit_index,
            pnl_usd=pnl,
            r_multiple=r_multiple,
            status=status,
        )
        self.trades.append(trade)
        return trade

    def trades_df(self) -> pl.DataFrame:
        if not self.trades:
            return pl.DataFrame()
        return pl.DataFrame(
            [
                {
                    "setup_name": t.setup_name,
                    "side": t.side,
                    "entry_ts_ny": t.entry_ts_ny,
                    "exit_ts_ny": t.exit_ts_ny,
                    "entry_price": t.entry_price,
                    "exit_price": t.exit_price,
                    "stop_loss": t.stop_loss,
                    "take_profit": t.take_profit,
                    "quantity": t.quantity,
                    "pnl_usd": t.pnl_usd,
                    "r_multiple": t.r_multiple,
                    "status": str(t.status),
                }
                for t in self.trades
            ],
        )

    def equity_df(self) -> pl.DataFrame:
        if not self.equity_series:
            return pl.DataFrame(schema={"ts_ny": pl.Datetime, "equity": pl.Float64})
        return pl.DataFrame(
            {
                "ts_ny": [t for t, _ in self.equity_series],
                "equity": [e for _, e in self.equity_series],
            },
        )
