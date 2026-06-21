"""Paper-trading broker: in-memory implementation of the Broker contract.

Tracks orders, fills (using last seen tick price), positions, and equity.
Designed to mirror the backtest engine's behavior for parity testing.
"""

from __future__ import annotations

from ict_bot.execution.broker import Broker, BrokerError, BrokerOrderAck, BrokerPosition


class PaperBroker(Broker):
    def __init__(self, *, starting_equity: float = 100_000.0,
                 tick_size: float = 0.25, tick_value_usd: float = 0.50,
                 commission_per_side_usd: float = 0.40,
                 slippage_ticks: int = 1) -> None:
        self._connected = False
        self._starting_equity = starting_equity
        self._equity = starting_equity
        self._tick_size = tick_size
        self._tick_value = tick_value_usd
        self._commission = commission_per_side_usd
        self._slippage = slippage_ticks
        self._last_price: dict[str, float] = {}
        self._positions: dict[str, BrokerPosition] = {}
        self._next_id = 1
        self._sl_tp_by_symbol: dict[str, tuple[float, float]] = {}

    @property
    def name(self) -> str:
        return "paper"

    def connect(self) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def feed_price(self, symbol: str, price: float) -> None:
        """Push the latest tick price; triggers SL/TP if breached."""
        self._last_price[symbol] = price
        if symbol not in self._positions or symbol not in self._sl_tp_by_symbol:
            return
        pos = self._positions[symbol]
        sl, tp = self._sl_tp_by_symbol[symbol]
        if pos.quantity > 0:
            if price <= sl:
                self._close(symbol, sl - self._slippage * self._tick_size)
            elif price >= tp:
                self._close(symbol, tp)
        elif pos.quantity < 0:
            if price >= sl:
                self._close(symbol, sl + self._slippage * self._tick_size)
            elif price <= tp:
                self._close(symbol, tp)

    def submit_market(self, symbol: str, side: str, quantity: int,
                       *, sl: float, tp: float) -> BrokerOrderAck:
        if not self._connected:
            raise BrokerError("paper broker not connected")
        if symbol not in self._last_price:
            return BrokerOrderAck(broker_order_id="", accepted=False,
                                  reason="no_price_feed")
        if symbol in self._positions:
            return BrokerOrderAck(broker_order_id="", accepted=False,
                                  reason="position_exists")
        fill_price = self._last_price[symbol] + (
            self._slippage * self._tick_size
            * (1 if side == "BUY" else -1)
        )
        signed_qty = quantity if side == "BUY" else -quantity
        self._positions[symbol] = BrokerPosition(
            symbol=symbol,
            quantity=signed_qty,
            avg_price=fill_price,
            unrealized_pnl_usd=0.0,
        )
        self._sl_tp_by_symbol[symbol] = (sl, tp)
        oid = f"paper-{self._next_id}"
        self._next_id += 1
        return BrokerOrderAck(broker_order_id=oid, accepted=True)

    def _close(self, symbol: str, exit_price: float) -> None:
        if symbol not in self._positions:
            return
        pos = self._positions.pop(symbol)
        self._sl_tp_by_symbol.pop(symbol, None)
        ticks_moved = (exit_price - pos.avg_price) / self._tick_size
        gross = ticks_moved * self._tick_value * pos.quantity
        commission = 2 * self._commission * abs(pos.quantity)
        self._equity += gross - commission

    def cancel_all(self, symbol: str | None = None) -> None:
        # Paper broker has no resting orders besides bracket SL/TP — no-op
        if symbol is not None and symbol in self._sl_tp_by_symbol:
            self._sl_tp_by_symbol.pop(symbol, None)
        elif symbol is None:
            self._sl_tp_by_symbol.clear()

    def flatten_all(self, symbol: str | None = None) -> None:
        targets = [symbol] if symbol else list(self._positions.keys())
        for s in targets:
            if s in self._last_price:
                self._close(s, self._last_price[s])

    def positions(self) -> list[BrokerPosition]:
        return list(self._positions.values())

    def equity_usd(self) -> float:
        unreal = 0.0
        for s, pos in self._positions.items():
            if s in self._last_price:
                ticks = (self._last_price[s] - pos.avg_price) / self._tick_size
                unreal += ticks * self._tick_value * pos.quantity
        return self._equity + unreal
