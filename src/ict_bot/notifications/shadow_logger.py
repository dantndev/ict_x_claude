"""Shadow signal logger — record every signal the bot detects, regardless
of whether it executed it or was filtered out by the session gate.

Use case: production runs in Silver-Bullet-only mode (B), but we want to
keep evaluating what would have happened in NY-AM + NY-PM + SB (mode C)
or all-killzones (mode A) on REAL live data. Every signal is appended to
`logs/shadow/<YYYY-MM-DD>.csv` with:

    ts_ny, setup, side, entry, sl, tp, rr, killzone_tag,
    in_mode_B, in_mode_C, in_mode_A, executed, skip_reason

So tomorrow we can answer "if I had switched to mode C this week, how
many more trades would I have taken and what would they have been?"
without having to re-run any backtest.

This is pure observability — never affects trade decisions.
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import IO, Any

from ict_bot.sessions.killzones import SessionsConfig
from ict_bot.sessions.sessions import session_tag_at
from ict_bot.signals.setups.base import Signal
from ict_bot.utils.logging import get_logger

log = get_logger(__name__)


_MODE_C_WINDOWS = frozenset(
    {"ny_am_kz", "ny_pm_kz", "silver_bullet_am", "silver_bullet_pm"},
)
_MODE_B_WINDOWS = frozenset({"silver_bullet_am", "silver_bullet_pm"})
_MODE_A_WINDOWS = frozenset(
    {"london_kz", "ny_am_kz", "ny_pm_kz",
     "silver_bullet_am", "silver_bullet_pm"},
)

_HEADER = (
    "ts_ny",
    "setup",
    "side",
    "entry_price",
    "stop_loss",
    "take_profit",
    "rr",
    "killzone_tag",
    "in_mode_A",
    "in_mode_B",
    "in_mode_C",
    "executed",
    "skip_reason",
    "notes",
)


class ShadowSignalLogger:
    """Thread-safe CSV writer for shadow signals."""

    def __init__(
        self,
        out_dir: Path,
        *,
        sessions_config: SessionsConfig | None = None,
    ) -> None:
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self._cfg = sessions_config or SessionsConfig()
        self._lock = Lock()
        self._current_path: Path | None = None
        self._current_date_iso: str | None = None
        self._handle: IO[str] | None = None
        self._writer: Any | None = None  # csv.writer has no public type

    def _rollover_if_needed(self, ts_ny: datetime) -> None:
        d = ts_ny.date().isoformat()
        if d == self._current_date_iso and self._handle is not None:
            return
        self._close_handle()
        path = self.out_dir / f"{d}.csv"
        write_header = not path.exists()
        self._handle = path.open("a", encoding="utf-8", newline="")
        self._writer = csv.writer(self._handle)
        if write_header:
            self._writer.writerow(_HEADER)
        self._current_path = path
        self._current_date_iso = d
        log.info("shadow_log_rollover", path=str(path))

    def _close_handle(self) -> None:
        if self._handle is not None:
            try:
                self._handle.flush()
                self._handle.close()
            finally:
                self._handle = None
                self._writer = None

    def close(self) -> None:
        with self._lock:
            self._close_handle()

    def record(
        self,
        signal: Signal,
        *,
        executed: bool,
        skip_reason: str = "",
        notes: str = "",
    ) -> None:
        """Append one row for `signal`. Safe to call from any thread."""
        with self._lock:
            self._rollover_if_needed(signal.ts_ny)
            assert self._writer is not None
            tag = session_tag_at(signal.ts_ny, self._cfg)
            self._writer.writerow(
                (
                    signal.ts_ny.isoformat(),
                    signal.setup_name,
                    str(signal.side),
                    f"{signal.entry_price:.4f}",
                    f"{signal.stop_loss:.4f}",
                    f"{signal.take_profit:.4f}",
                    f"{signal.rr:.3f}",
                    tag,
                    "1" if tag in _MODE_A_WINDOWS else "0",
                    "1" if tag in _MODE_B_WINDOWS else "0",
                    "1" if tag in _MODE_C_WINDOWS else "0",
                    "1" if executed else "0",
                    skip_reason,
                    notes,
                ),
            )
            if self._handle is not None:
                self._handle.flush()


__all__ = ["ShadowSignalLogger"]
