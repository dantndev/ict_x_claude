"""Telegram commander — long-poll listener for `/status /pause /resume /stop
/flatten /restart /help` commands. Port of `core/telegram_commander.py`.

Security:
- Only processes messages from the configured `chat_id`. All others ignored.
- Discards stale updates on startup so old commands don't fire.
- Runs in a daemon thread; commands are pushed to a queue that the main loop
  drains and executes (no shared mutable state with the trading thread).
"""

from __future__ import annotations

import threading
import time
from collections import deque

import httpx

from ict_bot.utils.logging import get_logger

log = get_logger(__name__)

KNOWN_COMMANDS: frozenset[str] = frozenset(
    {"status", "pause", "resume", "stop", "flatten", "restart", "help", "start"},
)


class TelegramCommander:
    def __init__(
        self,
        token: str | None,
        chat_id: str | None,
        *,
        enabled: bool = True,
        poll_timeout: int = 20,
    ) -> None:
        self.token = token or ""
        self.chat_id = str(chat_id or "")
        self.enabled = bool(enabled)
        self.poll_timeout = max(5, int(poll_timeout))
        self._activo = bool(self.enabled and self.token and self.chat_id)
        self._queue: deque[str] = deque()
        self._lock = threading.Lock()
        self._stop_evt = threading.Event()
        self._thread: threading.Thread | None = None
        self._offset: int | None = None
        if not self._activo and self.enabled:
            log.warning("telegram_commander_inactive",
                        reason="missing token or chat_id")

    @property
    def activo(self) -> bool:
        return self._activo

    def start(self) -> None:
        if not self._activo:
            return
        try:
            self._init_offset()
        except Exception as e:
            log.warning("telegram_offset_init_failed",
                        error=f"{type(e).__name__}: {e}")
        try:
            self._register_menu()
        except Exception as e:
            log.warning("telegram_menu_register_failed",
                        error=f"{type(e).__name__}: {e}")
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        log.info("telegram_commander_started")

    def stop(self) -> None:
        self._stop_evt.set()

    def poll_commands(self) -> list[str]:
        """Return and clear all queued commands."""
        with self._lock:
            cmds = list(self._queue)
            self._queue.clear()
        return cmds

    def _url(self, method: str) -> str:
        return f"https://api.telegram.org/bot{self.token}/{method}"

    def _init_offset(self) -> None:
        res = httpx.get(self._url("getUpdates"),
                         params={"timeout": 0}, timeout=10)
        if res.status_code == 200:
            data = res.json().get("result", [])
            if data:
                self._offset = data[-1]["update_id"] + 1

    def _register_menu(self) -> None:
        """Register the bot's command menu in the authorized chat."""
        if not self._activo:
            return
        comandos = [
            {"command": "status",
             "description": "Status: feed, position, daily PnL"},
            {"command": "pause",
             "description": "Stop taking entries (still alive)"},
            {"command": "resume",
             "description": "Resume taking entries"},
            {"command": "flatten",
             "description": "Close all open positions now"},
            {"command": "stop",
             "description": "Clean shutdown of the bot"},
            {"command": "restart",
             "description": "Restart (requires a supervisor process)"},
        ]
        scope_obj: dict[str, object]
        if self.chat_id.lstrip("-").isdigit():
            scope_obj = {"type": "chat", "chat_id": int(self.chat_id)}
        else:
            scope_obj = {"type": "default"}
        payload: dict[str, object] = {"commands": comandos, "scope": scope_obj}
        res = httpx.post(self._url("setMyCommands"), json=payload, timeout=10)
        if res.status_code == 200:
            log.info("telegram_menu_registered")

    def _run(self) -> None:
        while not self._stop_evt.is_set():
            try:
                params: dict[str, int] = {"timeout": self.poll_timeout}
                if self._offset is not None:
                    params["offset"] = self._offset
                res = httpx.get(
                    self._url("getUpdates"),
                    params=params,
                    timeout=self.poll_timeout + 10,
                )
                if res.status_code != 200:
                    time.sleep(3)
                    continue
                for u in res.json().get("result", []):
                    self._offset = u["update_id"] + 1
                    msg = u.get("message") or u.get("edited_message")
                    if not msg:
                        continue
                    chat = str(msg.get("chat", {}).get("id", ""))
                    if chat != self.chat_id:
                        continue
                    text = (msg.get("text") or "").strip()
                    if not text.startswith("/"):
                        continue
                    cmd = text.split()[0].lstrip("/").lower().split("@")[0]
                    if cmd in KNOWN_COMMANDS:
                        with self._lock:
                            self._queue.append(cmd)
                        log.info("telegram_command_received", cmd=cmd)
            except httpx.RequestError:
                time.sleep(3)
            except Exception as e:
                log.warning("telegram_commander_error",
                            error=f"{type(e).__name__}: {e}")
                time.sleep(3)
