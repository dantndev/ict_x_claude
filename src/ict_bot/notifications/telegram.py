"""Telegram async notifier — port of the production `notifier_telegram.py`.

NEVER blocks the trading loop: every send happens on a daemon thread.
Categories let the caller filter what gets pushed (e.g., only TRADE +
KILLSWITCH in production, everything in debug).
"""

from __future__ import annotations

import os
import threading
import time
from typing import Final

import httpx

from ict_bot.utils.logging import get_logger

log = get_logger(__name__)

EMOJI: Final[dict[str, str]] = {
    "sistema_inicio":   "[START]",
    "sistema_parada":   "[STOP]",
    "trade_enviado":    "[TRADE]",
    "trade_fallo":      "[TRADE X]",
    "trade_cerrado":    "[CERRADO]",
    "killswitch":       "[KILLSWITCH]",
    "heartbeat":        "[HEARTBEAT]",
    "error":            "[ERROR]",
    "feed_caido":       "[WARN]",
    "comando_ok":       "[CMD OK]",
    "comando_error":    "[CMD ERR]",
    "signal":           "[SIGNAL]",
    "pause":            "[PAUSE]",
    "resume":           "[RESUME]",
    "flatten":          "[FLATTEN]",
}


class TelegramNotifier:
    """Async notifier — never blocks the trading loop."""

    def __init__(
        self,
        token: str | None = None,
        chat_id: str | None = None,
        *,
        categorias_activas: set[str] | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.token = token or os.environ.get("TELEGRAM_TOKEN", "")
        self.chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")
        self.timeout = timeout
        self.activas = (
            set(categorias_activas) if categorias_activas is not None else set(EMOJI)
        )
        self._activo = bool(self.token and self.chat_id)
        if not self._activo:
            log.warning("telegram_disabled",
                        reason="missing TELEGRAM_TOKEN or TELEGRAM_CHAT_ID")

    @property
    def activo(self) -> bool:
        return self._activo

    def enviar(self, categoria: str, mensaje: str) -> None:
        """Fire-and-forget send. Returns immediately."""
        if not self._activo or (self.activas and categoria not in self.activas):
            return
        prefijo = EMOJI.get(categoria, "")
        texto = f"{prefijo} {mensaje}" if prefijo else mensaje
        threading.Thread(
            target=self._enviar_sync, args=(texto,), daemon=True,
        ).start()

    def _enviar_sync(self, texto: str) -> None:
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        for parse_mode in ("Markdown", None):
            payload: dict[str, str] = {"chat_id": self.chat_id, "text": texto}
            if parse_mode:
                payload["parse_mode"] = parse_mode
            for intento in range(3):
                try:
                    res = httpx.post(url, json=payload, timeout=self.timeout)
                    if res.status_code == 200:
                        return
                    if res.status_code == 400 and parse_mode == "Markdown":
                        break  # try plain text
                    if res.status_code == 429:
                        time.sleep(1.0)
                        continue
                    log.warning("telegram_http_error", status=res.status_code,
                                body=res.text[:120])
                    return
                except httpx.RequestError as e:
                    if intento < 2:
                        time.sleep(0.5 * (intento + 1))
                        continue
                    log.warning("telegram_error",
                                error=f"{type(e).__name__}: {e}")
                    return
