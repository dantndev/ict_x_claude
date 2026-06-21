"""Live runner: orchestrates detectors → setups → broker for a streaming bar feed.

The runner accepts an iterator of incoming bars (e.g., polled from the local
backtest API every minute, or from a websocket feed in production), runs the
pipeline incrementally on the trailing window, and submits matching Signals to
the broker via the Broker contract.

Includes:
- Killzone / news / lunch / midnight-open gating (reuses sessions module).
- Daily loss + consecutive-loss tracking (reuses LimitsState).
- Kill switch.
- Force-flatten at 16:30 NY.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime

from ict_bot.backtest.runner import detect_all_signals
from ict_bot.data.models import Bars
from ict_bot.execution.broker import Broker
from ict_bot.execution.kill_switch import KillSwitch, KillSwitchTripped
from ict_bot.notifications.shadow_logger import ShadowSignalLogger
from ict_bot.risk.limits import LimitsConfig, LimitsState
from ict_bot.risk.sizing import InstrumentSpec, RiskConfig, size_position
from ict_bot.sessions.killzones import (
    SessionsConfig,
    force_flat,
    new_entries_allowed,
)
from ict_bot.sessions.midnight_open import (
    midnight_open_filter_long,
    midnight_open_filter_short,
)
from ict_bot.signals.setups.base import TradeSide
from ict_bot.utils.logging import get_logger
from ict_bot.utils.tz import to_ny

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class LiveConfig:
    symbol: str = "MNQM6"
    starting_equity: float = 100_000.0
    enforce_killzones: bool = True
    enforce_midnight_filter: bool = True
    enforce_force_flat: bool = True


@dataclass(slots=True)
class LiveRunner:
    broker: Broker
    config: LiveConfig
    instrument: InstrumentSpec = field(default_factory=InstrumentSpec)
    risk: RiskConfig = field(default_factory=RiskConfig)
    limits: LimitsConfig = field(default_factory=LimitsConfig)
    sessions_config: SessionsConfig = field(default_factory=SessionsConfig)
    kill_switch: KillSwitch = field(default_factory=KillSwitch)
    shadow_logger: ShadowSignalLogger | None = None  # records ALL signals (B+C+A)
    state: LimitsState = field(default_factory=LimitsState)
    seen_bar_signal_indices: set[int] = field(default_factory=set)
    last_mid_open: float | None = None
    last_mid_open_day: date | None = None
    paused: bool = False           # remote /pause toggle
    stop_requested: bool = False   # remote /stop toggle

    def on_bars_window(self, bars_window: Bars) -> None:
        """Re-run detectors over the trailing window and act on the latest signals."""
        if bars_window.empty:
            return
        last_ts = bars_window.last_ts()
        assert last_ts is not None
        ts_ny = to_ny(last_ts)
        today = ts_ny.date()

        # Day rollover + Midnight Open extraction
        if self.state.current_day != today:
            self.state.reset_for_day(today, self.broker.equity_usd())
            self._compute_midnight_open(bars_window, today)

        # Force-flatten window (does NOT block detection — we still want to
        # log shadow signals around 16:30).
        if self.config.enforce_force_flat and force_flat(last_ts, self.sessions_config):
            log.info("force_flat_triggered")
            self.broker.flatten_all()
            return

        # Detect ALL candidate signals first (independent of any filter) so
        # the shadow logger sees them — this lets us evaluate alternative
        # session modes after the fact (mode A / C analysis while running B).
        signals = detect_all_signals(bars_window)
        latest_idx = len(bars_window) - 1
        bar_signals = [s for s in signals if s.bar_index == latest_idx
                       and s.bar_index not in self.seen_bar_signal_indices]

        # Decide why an entry would be blocked (single source of truth).
        gate_reason = self._gate_reason(last_ts)

        for s in bar_signals:
            mid_reason = self._midnight_reason(s)
            reason = gate_reason or mid_reason or ""
            if reason:
                self._record_shadow(s, executed=False, reason=reason)
                continue
            qty = size_position(
                self.broker.equity_usd(), s.entry_price, s.stop_loss,
                instrument=self.instrument, risk=self.risk,
            )
            if qty == 0:
                self._record_shadow(s, executed=False, reason="sizing_zero")
                continue
            ack = self.broker.submit_market(
                self.config.symbol, side=str(s.side), quantity=qty,
                sl=s.stop_loss, tp=s.take_profit,
            )
            self.seen_bar_signal_indices.add(s.bar_index)
            self._record_shadow(
                s, executed=ack.accepted,
                reason="" if ack.accepted else (ack.reason or "broker_rejected"),
                notes=f"qty={qty} ticket={ack.broker_order_id}",
            )
            log.info("order_submitted", setup=s.setup_name, side=str(s.side),
                     qty=qty, accepted=ack.accepted,
                     broker_order_id=ack.broker_order_id)

    def _gate_reason(self, last_ts: datetime) -> str:
        """Return the first reason that blocks new entries, or '' if open."""
        if self.paused:
            return "paused"
        if self.config.enforce_killzones and \
                not new_entries_allowed(last_ts, self.sessions_config):
            return "outside_allowed_window"
        if not self.state.can_trade(config=self.limits):
            return "limits_lock"
        try:
            self.kill_switch.assert_armed()
        except KillSwitchTripped:
            return f"kill_switch:{self.kill_switch.reason}"
        return ""

    def _midnight_reason(self, signal: object) -> str:
        if not self.config.enforce_midnight_filter:
            return ""
        from ict_bot.signals.setups.base import Signal as _Signal
        if not isinstance(signal, _Signal):
            return ""
        if signal.side == TradeSide.BUY and not midnight_open_filter_long(
            signal.entry_price, self.last_mid_open,
        ):
            return "mid_open_filter_long"
        if signal.side == TradeSide.SELL and not midnight_open_filter_short(
            signal.entry_price, self.last_mid_open,
        ):
            return "mid_open_filter_short"
        return ""

    def _record_shadow(
        self, signal: object, *,
        executed: bool, reason: str = "", notes: str = "",
    ) -> None:
        if self.shadow_logger is None:
            return
        from ict_bot.signals.setups.base import Signal as _Signal
        if not isinstance(signal, _Signal):
            return
        try:
            self.shadow_logger.record(
                signal, executed=executed, skip_reason=reason, notes=notes,
            )
        except Exception as e:
            log.warning("shadow_logger_error", error=f"{type(e).__name__}: {e}")

    def _compute_midnight_open(self, bars_window: Bars, today: date) -> None:
        # Find first bar of `today` at 00:00 NY
        df = bars_window.df
        match = df.filter(
            (df["ts_ny"].dt.date() == today)
            & (df["ts_ny"].dt.hour() == 0)
            & (df["ts_ny"].dt.minute() == 0),
        )
        if match.is_empty():
            self.last_mid_open = None
        else:
            self.last_mid_open = float(match["open"][0])
        self.last_mid_open_day = today

    def run(self, bar_stream: Iterable[Bars]) -> None:
        """Convenience: consume an iterable of trailing-window Bars."""
        for bars_window in bar_stream:
            self.on_bars_window(bars_window)
