"""Abstract broker interface — every concrete broker (paper, IBKR, Tradovate,
Rithmic, ...) implements this contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class BrokerError(Exception):
    """Raised by brokers on connection / order / data errors."""


@dataclass(frozen=True, slots=True)
class BrokerOrderAck:
    broker_order_id: str
    accepted: bool
    reason: str = ""


@dataclass(frozen=True, slots=True)
class BrokerPosition:
    symbol: str
    quantity: int        # signed
    avg_price: float
    unrealized_pnl_usd: float


class Broker(ABC):
    """Minimal contract every broker must implement."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def is_connected(self) -> bool: ...

    @abstractmethod
    def submit_market(self, symbol: str, side: str, quantity: int,
                       *, sl: float, tp: float) -> BrokerOrderAck: ...

    @abstractmethod
    def cancel_all(self, symbol: str | None = None) -> None: ...

    @abstractmethod
    def flatten_all(self, symbol: str | None = None) -> None: ...

    @abstractmethod
    def positions(self) -> list[BrokerPosition]: ...

    @abstractmethod
    def equity_usd(self) -> float: ...
