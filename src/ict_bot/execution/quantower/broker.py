"""Quantower broker adapter — wraps DOM2 (data) + Lucid (executor) under the
generic `Broker` contract so the rest of the bot (LiveRunner, ML filter, ...)
can stay broker-agnostic.

Symbol split (matches the production setup):
- DATA  is read from `ENQM26` (E-mini NQ) on the DOM2 bridge.
- ORDERS are sent on `MNQM6` (Micro NQ) via the Lucid executor.

The micro contract is $2/point, $0.50/tick — much smaller P&L per move, the
right size for the $25k / $1k DD prop account.
"""

from __future__ import annotations

from ict_bot.execution.broker import Broker, BrokerError, BrokerOrderAck, BrokerPosition
from ict_bot.execution.quantower.dom2_client import DOM2Client, DOM2Snapshot
from ict_bot.execution.quantower.lucid_executor import LucidExecutor
from ict_bot.utils.logging import get_logger

log = get_logger(__name__)


class QuantowerBroker(Broker):
    """Wires the DOM2 feed + Lucid executor into one Broker."""

    def __init__(
        self,
        *,
        dom2_url: str = "http://localhost:8080/dom2",
        lucid_url: str = "http://localhost:6001",
        data_symbol: str = "ENQM26",
        exec_symbol: str = "MNQM6",
        tick_size: float = 0.25,
        tick_value_usd: float = 0.50,
        qty_default: int = 1,
        dry_run: bool = False,
    ) -> None:
        self.data_symbol = data_symbol
        self.exec_symbol = exec_symbol
        self.tick_size = tick_size
        self.tick_value_usd = tick_value_usd
        self.feed = DOM2Client(url=dom2_url)
        self.executor = LucidExecutor(
            url_base=lucid_url,
            symbol=exec_symbol,
            qty_default=qty_default,
            dry_run=dry_run,
        )
        self._connected = False
        self._last_snapshot: DOM2Snapshot | None = None

    @property
    def name(self) -> str:
        return "quantower"

    def connect(self) -> None:
        ok_health = self.executor.inicializar()
        snap = self.feed.leer()
        if snap is None:
            log.warning("quantower_feed_no_initial_snapshot")
        else:
            self._last_snapshot = snap
        self._connected = bool(ok_health)
        log.info("quantower_connect",
                 data_symbol=self.data_symbol, exec_symbol=self.exec_symbol,
                 health_ok=ok_health, feed_alive=snap is not None)

    def disconnect(self) -> None:
        try:
            self.feed.close()
            self.executor.close()
        finally:
            self._connected = False

    def is_connected(self) -> bool:
        return self._connected and self.feed.vivo()

    def latest_snapshot(self) -> DOM2Snapshot | None:
        """Pull the latest DOM2 snapshot (the LiveRunner ticks at its own rate)."""
        snap = self.feed.leer()
        if snap is not None:
            self._last_snapshot = snap
        return snap

    def submit_market(
        self,
        symbol: str,
        side: str,
        quantity: int,
        *,
        sl: float,
        tp: float,
    ) -> BrokerOrderAck:
        """Submit a market order with bracket SL/TP at PRICE levels (not points).

        The Lucid bridge accepts SL/TP as distances in points; we convert from
        the absolute prices the engine speaks. Entry reference = mid of the
        most recent snapshot.
        """
        if not self._connected:
            raise BrokerError("quantower broker not connected")
        if symbol != self.exec_symbol:
            raise BrokerError(
                f"order symbol {symbol!r} != configured exec_symbol {self.exec_symbol!r}",
            )
        snap = self.latest_snapshot()
        if snap is None:
            return BrokerOrderAck(broker_order_id="", accepted=False,
                                    reason="no_feed_price")
        ref_price = snap.precio
        sl_pts = abs(ref_price - sl)
        tp_pts = abs(tp - ref_price)
        if sl_pts <= 0 or tp_pts <= 0:
            return BrokerOrderAck(broker_order_id="", accepted=False,
                                    reason="invalid_bracket_distance")
        direccion = "LONG" if side.upper() == "BUY" else "SHORT"
        res = self.executor.enviar_orden(
            direccion=direccion,
            sl_pts=sl_pts,
            tp_pts=tp_pts,
            qty_override=quantity,
            etiqueta="ict_x_claude_live",
        )
        return BrokerOrderAck(
            broker_order_id=res.ticket,
            accepted=res.exitoso,
            reason=res.mensaje,
        )

    def cancel_all(self, symbol: str | None = None) -> None:
        _ = symbol  # bridge has no per-symbol cancel
        self.executor.flatten()

    def flatten_all(self, symbol: str | None = None) -> None:
        _ = symbol
        ok = self.executor.flatten()
        log.info("quantower_flatten", ok=ok)

    def positions(self) -> list[BrokerPosition]:
        data = self.executor.obtener_posicion()
        if not data:
            return []
        # Bridge returns a single-position snapshot for the configured symbol
        qty_raw = data.get("qty", data.get("position", data.get("net_qty", 0))) or 0
        try:
            qty = int(qty_raw)
        except (TypeError, ValueError):
            qty = 0
        if qty == 0:
            return []
        avg_raw = data.get("avg_price", data.get("entry_price", 0.0)) or 0.0
        unrl_raw = data.get("pnl_unrealized", data.get("unrealized", 0.0)) or 0.0
        try:
            avg = float(avg_raw)
            unrl = float(unrl_raw)
        except (TypeError, ValueError):
            avg, unrl = 0.0, 0.0
        return [BrokerPosition(symbol=self.exec_symbol, quantity=qty,
                                avg_price=avg, unrealized_pnl_usd=unrl)]

    def equity_usd(self) -> float:
        """Account equity — best-effort from /position payload; otherwise NaN.

        The Lucid bridge does not expose account equity directly; we report the
        sum of position unrealized PnL only. The LiveRunner is expected to
        snapshot starting equity from the user's prop-firm dashboard at
        session start and add `unrealized` for tracking.
        """
        data = self.executor.obtener_posicion()
        if not data:
            return float("nan")
        eq = data.get("account_equity", data.get("equity"))
        try:
            return float(eq) if eq is not None else float("nan")
        except (TypeError, ValueError):
            return float("nan")
