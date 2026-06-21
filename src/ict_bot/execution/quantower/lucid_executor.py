"""Lucid executor client — POSTs orders to the Quantower→Rithmic bridge at /orders.

Port of the production `core/lucid_executor.py`. The bridge code lives inside
Quantower and CANNOT be modified — this client only sends/receives via the
documented endpoints:

    GET  /health           → bridge capabilities (runner_support, max_net_qty, ...)
    POST /orders           → submit a bracketed order
    GET  /position         → current position snapshot (qty, avg_price, unrealized)
    POST /modify_sl        → move stop loss for an open ticket
    POST /flatten          → close all positions

Order payload (sent to /orders):
    {
      "signal_id":    "<unique>",
      "symbol":       "MNQM6",
      "side":         "BUY" | "SELL",
      "qty":          <int>,
      "sl_pts":       <float, distance in points>,
      "tp_pts":       <float, distance in points>,
      "strategy_tag": "<free text>"
    }

Response:
    {"ok": true,  "signal_id": "...", "fill_price": <float>, "status": "..."}
    {"ok": false, "error": "..."}                                # rejection
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx

from ict_bot.utils.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ResultadoOrden:
    exitoso: bool
    ticket: str = ""
    mensaje: str = ""
    precio_entrada: float = 0.0
    latencia_ms: float = 0.0


@dataclass(frozen=True, slots=True)
class BridgeCapabilities:
    runner_support: bool = False
    same_direction_adds_support: bool = False
    multi_entry_safe: bool = False
    max_net_qty: int = 0


class LucidExecutor:
    def __init__(
        self,
        url_base: str = "http://localhost:6001",
        symbol: str = "MNQM6",
        qty_default: int = 1,
        timeout_sec: float = 5.0,
        dry_run: bool = False,
    ) -> None:
        self.base_url = url_base.rstrip("/")
        self.url_orders = f"{self.base_url}/orders"
        self.url_health = f"{self.base_url}/health"
        self.url_position = f"{self.base_url}/position"
        self.url_modify_sl = f"{self.base_url}/modify_sl"
        self.url_flatten = f"{self.base_url}/flatten"
        self.symbol = symbol
        self.qty_default = qty_default
        self.timeout = timeout_sec
        self.dry_run = dry_run
        self.capabilities = BridgeCapabilities()
        self._client = httpx.Client(timeout=timeout_sec)

    def close(self) -> None:
        self._client.close()

    def inicializar(self) -> bool:
        """Probe /health and store bridge capabilities. Always returns True
        (we proceed optimistically; failures will show up on /orders)."""
        try:
            res = self._client.get(self.url_health, timeout=2.0)
            if res.status_code == 200:
                try:
                    data = res.json()
                    self.capabilities = BridgeCapabilities(
                        runner_support=bool(data.get("runner_support", False)),
                        same_direction_adds_support=bool(
                            data.get("same_direction_adds_support", False),
                        ),
                        multi_entry_safe=bool(data.get("multi_entry_safe", False)),
                        max_net_qty=int(data.get("max_net_qty", 0) or 0),
                    )
                except Exception:
                    pass
                log.info("lucid_health_ok", symbol=self.symbol,
                         caps=self.capabilities.__dict__)
                return True
        except Exception as e:
            log.warning("lucid_health_failed", error=str(e),
                        note="continuing optimistic")
        return True

    def _build_payload(
        self,
        direccion: str,
        qty: int,
        sl_pts: float,
        tp_pts: float,
        etiqueta: str = "",
        signal_id: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "signal_id": signal_id or f"ict_{int(time.time() * 1000)}",
            "symbol": self.symbol,
            "side": "BUY" if direccion.upper() in {"LONG", "BUY"} else "SELL",
            "qty": qty,
            "sl_pts": sl_pts,
            "tp_pts": tp_pts,
            "strategy_tag": etiqueta or "ict_x_claude",
        }
        if extra:
            payload.update(extra)
        return payload

    def enviar_orden(
        self,
        direccion: str,
        sl_pts: float,
        tp_pts: float,
        *,
        etiqueta: str = "",
        qty_override: int | None = None,
        signal_id: str | None = None,
    ) -> ResultadoOrden:
        """Send a simple bracketed order. Returns ResultadoOrden with fill/ticket."""
        qty = int(qty_override) if qty_override is not None else self.qty_default

        if self.dry_run:
            log.info("dry_run_order", direccion=direccion, qty=qty,
                     sl_pts=sl_pts, tp_pts=tp_pts)
            return ResultadoOrden(
                exitoso=True, ticket=f"dryrun_{int(time.time())}",
                mensaje="dry-run",
            )

        payload = self._build_payload(direccion, qty, sl_pts, tp_pts,
                                       etiqueta, signal_id)
        t0 = time.time()
        try:
            res = self._client.post(self.url_orders, json=payload)
            latencia = (time.time() - t0) * 1000
        except Exception as e:
            log.error("lucid_post_error", error=f"{type(e).__name__}: {e}")
            return ResultadoOrden(
                exitoso=False, mensaje=f"{type(e).__name__}:{e}",
            )

        if res.status_code != 200:
            msg = f"HTTP {res.status_code}: {res.text[:120]}"
            log.warning("lucid_order_failed", msg=msg, latencia_ms=latencia)
            return ResultadoOrden(exitoso=False, mensaje=msg, latencia_ms=latencia)

        try:
            data = res.json()
        except Exception:
            return ResultadoOrden(exitoso=False, mensaje="invalid_json",
                                    latencia_ms=latencia)

        if data.get("ok", True) is False:
            err = data.get("error", data.get("rejected",
                          data.get("status", data.get("msg", "rejected"))))
            log.warning("lucid_order_rejected", err=str(err), latencia_ms=latencia)
            return ResultadoOrden(exitoso=False, mensaje=str(err),
                                    latencia_ms=latencia)

        ticket = str(data.get("signal_id",
                              data.get("ticket", data.get("order_id", ""))))
        precio = float(data.get("fill_price", data.get("precio_entrada", 0.0)))
        log.info("lucid_order_ok", side=payload["side"], qty=qty,
                 ticket=ticket, latencia_ms=int(latencia))
        return ResultadoOrden(
            exitoso=True, ticket=ticket, precio_entrada=precio,
            latencia_ms=latencia,
            mensaje=str(data.get("status", data.get("msg", "OK"))),
        )

    def modificar_sl(self, signal_id: str, nuevo_sl: float) -> bool:
        payload = {"signal_id": signal_id, "new_sl_price": nuevo_sl}
        try:
            res = self._client.post(self.url_modify_sl, json=payload)
            if res.status_code == 200:
                data = res.json()
                return bool(data.get("ok", False))
        except Exception as e:
            log.error("modify_sl_error", error=str(e))
        return False

    def obtener_posicion(self) -> dict[str, Any]:
        try:
            res = self._client.get(self.url_position)
            if res.status_code == 200:
                return res.json()  # type: ignore[no-any-return]
        except Exception as e:
            log.error("obtener_posicion_error", error=str(e))
        return {}

    def flatten(self) -> bool:
        try:
            res = self._client.post(self.url_flatten)
            if res.status_code == 200:
                data = res.json()
                return bool(data.get("ok", False))
        except Exception as e:
            log.error("flatten_error", error=str(e))
        return False
