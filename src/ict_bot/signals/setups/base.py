"""Shared types for setup composition.

A `Signal` is the deterministic, auditable output of a setup. It carries the
trade direction, entry / SL / TP prices, the list of PD-array components that
produced it, and gating flags (HTF anchor, killzone, midnight-open filter).

The backtest engine (Phase 5) consumes Signals; setups never place orders
themselves.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from ict_bot.signals.base import Direction


class TradeSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass(frozen=True, slots=True)
class Signal:
    """A trade intent from a setup, ready for the risk + execution layer."""

    setup_name: str
    side: TradeSide
    direction: Direction
    entry_price: float
    stop_loss: float
    take_profit: float
    ts_ny: datetime               # bar at which the setup became actionable
    bar_index: int
    components: tuple[object, ...] = field(default_factory=tuple)
    htf_anchored: bool = True
    in_killzone: bool = True
    midnight_filter_ok: bool = True
    confidence: float = 0.0
    notes: str = ""

    @property
    def risk(self) -> float:
        return abs(self.entry_price - self.stop_loss)

    @property
    def reward(self) -> float:
        return abs(self.take_profit - self.entry_price)

    @property
    def rr(self) -> float:
        r = self.risk
        return self.reward / r if r > 0 else 0.0
