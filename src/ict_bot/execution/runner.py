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
from datetime import date

from ict_bot.backtest.runner import detect_all_signals
from ict_bot.data.models import Bars
from ict_bot.execution.broker import Broker
from ict_bot.execution.kill_switch import KillSwitch, KillSwitchTripped
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
    state: LimitsState = field(default_factory=LimitsState)
    seen_bar_signal_indices: set[int] = field(default_factory=set)
    last_mid_open: float | None = None
    last_mid_open_day: date | None = None
    paused: bool = False           # remote /pause toggle
    stop_requested: bool = False   # remote /stop toggle

    def on_bars_window(self, bars_window: Bars) -> None:  # noqa: PLR0912
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

        # Force-flatten window
        if self.config.enforce_force_flat and force_flat(last_ts, self.sessions_config):
            log.info("force_flat_triggered")
            self.broker.flatten_all()
            return

        # Gates that block new orders
        if self.paused:
            return
        if self.config.enforce_killzones and \
                not new_entries_allowed(last_ts, self.sessions_config):
            return
        if not self.state.can_trade(config=self.limits):
            return
        try:
            self.kill_switch.assert_armed()
        except KillSwitchTripped:
            log.warning("kill_switch_blocking_orders", reason=self.kill_switch.reason)
            return

        # Detect signals; only act on those whose bar_index is the last bar (just closed)
        signals = detect_all_signals(bars_window)
        latest_idx = len(bars_window) - 1
        for s in signals:
            if s.bar_index != latest_idx:
                continue
            if s.bar_index in self.seen_bar_signal_indices:
                continue
            if self.config.enforce_midnight_filter:
                if s.side == TradeSide.BUY and not midnight_open_filter_long(
                    s.entry_price, self.last_mid_open,
                ):
                    continue
                if s.side == TradeSide.SELL and not midnight_open_filter_short(
                    s.entry_price, self.last_mid_open,
                ):
                    continue
            qty = size_position(
                self.broker.equity_usd(), s.entry_price, s.stop_loss,
                instrument=self.instrument, risk=self.risk,
            )
            if qty == 0:
                continue
            ack = self.broker.submit_market(
                self.config.symbol, side=str(s.side), quantity=qty,
                sl=s.stop_loss, tp=s.take_profit,
            )
            self.seen_bar_signal_indices.add(s.bar_index)
            log.info("order_submitted", setup=s.setup_name, side=str(s.side),
                     qty=qty, accepted=ack.accepted, broker_order_id=ack.broker_order_id)

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
