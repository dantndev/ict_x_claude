"""Order, Fill, Position, Trade — the contract between setups and the engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class OrderStatus(StrEnum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class PositionStatus(StrEnum):
    OPEN = "OPEN"
    CLOSED_TP = "CLOSED_TP"
    CLOSED_SL = "CLOSED_SL"
    CLOSED_FLAT = "CLOSED_FLAT"   # force-flatten at session end
    CLOSED_MANUAL = "CLOSED_MANUAL"


@dataclass(slots=True)
class Order:
    """A limit / market order pending fill."""

    order_id: int
    setup_name: str
    side: str               # "BUY" or "SELL"
    entry_price: float
    stop_loss: float
    take_profit: float
    quantity: int           # contracts
    submitted_at_index: int
    submitted_ts_ny: datetime
    status: OrderStatus = OrderStatus.PENDING
    expires_at_index: int | None = None


@dataclass(slots=True)
class Fill:
    order_id: int
    fill_price: float
    fill_index: int
    fill_ts_ny: datetime
    commission_usd: float = 0.0
    slippage_ticks: int = 0


@dataclass(slots=True)
class Position:
    position_id: int
    order: Order
    fill: Fill
    quantity: int            # signed: + for long, - for short
    status: PositionStatus = PositionStatus.OPEN
    exit_price: float | None = None
    exit_index: int | None = None
    exit_ts_ny: datetime | None = None
    pnl_usd: float = 0.0


@dataclass(slots=True)
class Trade:
    """A round-trip trade — collapsed view used for reporting."""

    setup_name: str
    side: str
    entry_price: float
    exit_price: float
    stop_loss: float
    take_profit: float
    quantity: int
    entry_ts_ny: datetime
    exit_ts_ny: datetime
    entry_index: int
    exit_index: int
    pnl_usd: float
    r_multiple: float
    status: PositionStatus
    setup_components: tuple[object, ...] = field(default_factory=tuple)
