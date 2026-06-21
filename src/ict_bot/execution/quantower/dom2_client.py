"""DOM2 client — reads the Quantower DomTransmitter bridge at /dom2.

Port of the production `core/dom2_client.py` from the previous bot, adapted to
this project's logging/types. The JSON shape exposed by the Quantower bridge
is treated as a black box that we MUST NOT modify; this client only consumes.

JSON shape (nested):
    {
      "microstructure": {"mid_price", "best_bid", "best_ask",
                          "spread_pts", "tick_velocity"},
      "footprint":      {"bid_vol", "ask_vol", "delta",
                          # legacy aliases: fp_bid_vol/fp_ask_vol/fp_delta, velocity},
      "dom":            {"bids": [{"s|size|qty|quantity|volume|v": ...}, ...],
                          "asks": [...]}
    }

The data symbol on the bridge is ENQM26 (E-mini NQ); execution is done on the
Micro contract (MNQM6 via the Lucid executor).
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from ict_bot.utils.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class DOM2Snapshot:
    ts_recepcion: float
    precio: float
    best_bid: float
    best_ask: float
    spread_pts: float
    bid_top5: float = 0.0
    ask_top5: float = 0.0
    bid_top10: float = 0.0
    ask_top10: float = 0.0
    bid_top20: float = 0.0
    ask_top20: float = 0.0
    bid_top40: float = 0.0
    ask_top40: float = 0.0
    fp_bid_vol: float = 0.0
    fp_ask_vol: float = 0.0
    tick_velocity: float = 0.0
    delta_acumulado: float = 0.0


def _level_size(level: object) -> float:
    """Extract size from a DOM level, tolerating the bridge's key variants."""
    if not isinstance(level, dict):
        return 0.0
    for key in ("s", "size", "qty", "quantity", "volume", "v"):
        try:
            value = level.get(key)
            if value is not None and value != "":
                return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def _sum_depth(levels: object, depth: int) -> float:
    if not isinstance(levels, list) or depth <= 0:
        return 0.0
    return sum(_level_size(level) for level in levels[:depth])


class DOM2Client:
    """HTTP client for the Quantower DOM2 bridge."""

    def __init__(
        self,
        url: str = "http://localhost:8080/dom2",
        timeout_sec: float = 2.0,
    ) -> None:
        self.url = url
        self.timeout = timeout_sec
        self._fallos = 0
        self._ultimo_ok = 0.0
        self._client = httpx.Client(timeout=timeout_sec)

    def close(self) -> None:
        self._client.close()

    def leer(self) -> DOM2Snapshot | None:
        """One snapshot read. Returns None on transient errors; logs every 50."""
        try:
            res = self._client.get(self.url)
            if res.status_code != 200:
                self._fallos += 1
                if self._fallos % 50 == 1:
                    log.warning("dom2_http_error", status=res.status_code,
                                fallos=self._fallos)
                return None

            data = res.json()
            micro = data.get("microstructure", {})
            fp = data.get("footprint", {})
            dom = data.get("dom", {})

            bid = float(micro.get("best_bid", 0))
            ask = float(micro.get("best_ask", 0))
            if bid <= 0 or ask <= 0:
                return None

            precio = float(micro.get("mid_price", (bid + ask) / 2))
            spread = float(micro.get("spread_pts", ask - bid))

            bids_list = dom.get("bids", [])
            asks_list = dom.get("asks", [])

            self._fallos = 0
            self._ultimo_ok = time.time()

            fp_bid = float(fp.get("bid_vol", fp.get("fp_bid_vol", 0)))
            fp_ask = float(fp.get("ask_vol", fp.get("fp_ask_vol", 0)))
            fp_delta = float(fp.get("delta", fp.get("fp_delta", fp_ask - fp_bid)))

            return DOM2Snapshot(
                ts_recepcion=self._ultimo_ok,
                precio=precio,
                best_bid=bid,
                best_ask=ask,
                spread_pts=spread,
                bid_top5=_sum_depth(bids_list, 5),
                ask_top5=_sum_depth(asks_list, 5),
                bid_top10=_sum_depth(bids_list, 10),
                ask_top10=_sum_depth(asks_list, 10),
                bid_top20=_sum_depth(bids_list, 20),
                ask_top20=_sum_depth(asks_list, 20),
                bid_top40=_sum_depth(bids_list, 40),
                ask_top40=_sum_depth(asks_list, 40),
                fp_bid_vol=fp_bid,
                fp_ask_vol=fp_ask,
                tick_velocity=float(fp.get("velocity", micro.get("tick_velocity", 0))),
                delta_acumulado=fp_delta,
            )

        except httpx.RequestError as e:
            self._fallos += 1
            if self._fallos % 50 == 1:
                log.warning("dom2_unreachable", error=type(e).__name__,
                            fallos=self._fallos)
            return None
        except Exception as e:
            log.error("dom2_error", error=f"{type(e).__name__}: {e}")
            return None

    def vivo(self, freshness_sec: float = 10.0) -> bool:
        """True if the last successful read happened within `freshness_sec`."""
        return (time.time() - self._ultimo_ok) < freshness_sec
