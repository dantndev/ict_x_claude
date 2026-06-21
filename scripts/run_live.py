"""LIVE runner — connects the ICT pipeline to the Quantower (DOM2 + Lucid) bridges.

Pre-flight checklist (the script halts if any fails):
    1. DOM2 reachable, returning a valid snapshot.
    2. Lucid /health responds.
    3. Config file loaded and prop-firm caps parsed.

Loop:
    - Read DOM2 snapshot every `poll_hz` Hz.
    - Aggregate into 1-minute bars (mid price = (bid+ask)/2).
    - On every bar close, hand the rolling Bars window to LiveRunner.
    - LiveRunner runs detectors → setups → gates → broker.submit_market.

Safety:
    - Hard daily loss limit + consecutive-loss limit from configs/lucid_propfirm.yaml.
    - Force-flatten at 16:30 NY.
    - Kill switch on any uncaught exception (positions are flattened, runner exits).

Usage:
    python scripts/run_live.py                       # full live (real money)
    python scripts/run_live.py --dry-run             # wiring only, no orders
    python scripts/run_live.py --confirm LIVE        # required to actually send orders
"""

from __future__ import annotations

import argparse
import io
import signal as os_signal
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import polars as pl
import yaml

from ict_bot.config.settings import REPO_ROOT
from ict_bot.data.models import Bars
from ict_bot.execution.kill_switch import KillSwitch
from ict_bot.execution.quantower import QuantowerBroker
from ict_bot.execution.runner import LiveConfig, LiveRunner
from ict_bot.notifications import TelegramCommander, TelegramNotifier
from ict_bot.risk.limits import LimitsConfig
from ict_bot.risk.sizing import InstrumentSpec, RiskConfig
from ict_bot.utils.logging import configure_logging, get_logger
from ict_bot.utils.tz import NY, to_ny

if isinstance(sys.stdout, io.TextIOWrapper):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]


def _load_config(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


class _BarAggregator:
    """Build 1-minute OHLCV bars from incoming DOM2 snapshots (mid price)."""

    def __init__(self, *, symbol: str, window_minutes: int = 240) -> None:
        self.symbol = symbol
        self.window_minutes = window_minutes
        self._current_minute: datetime | None = None
        self._o: float | None = None
        self._h: float | None = None
        self._l: float | None = None
        self._c: float | None = None
        self._v: int = 0
        self._closed_rows: list[dict] = []

    def feed(self, ts_ny: datetime, price: float) -> Bars | None:
        """Update with a new mid price; return a fresh `Bars` if a bar just closed."""
        minute = ts_ny.replace(second=0, microsecond=0)
        bar_closed = False
        if self._current_minute is None:
            self._current_minute = minute
            self._o = self._h = self._l = self._c = price
            self._v = 1
            return None
        if minute > self._current_minute:
            assert self._o is not None
            self._closed_rows.append(
                {
                    "ts_ny": self._current_minute,
                    "open": self._o,
                    "high": self._h,
                    "low": self._l,
                    "close": self._c,
                    "volume": self._v,
                },
            )
            cutoff = minute - timedelta(minutes=self.window_minutes)
            self._closed_rows = [r for r in self._closed_rows if r["ts_ny"] >= cutoff]
            self._current_minute = minute
            self._o = self._h = self._l = self._c = price
            self._v = 1
            bar_closed = True
        else:
            self._c = price
            self._h = max(self._h or price, price)
            self._l = min(self._l or price, price)
            self._v += 1
        if not bar_closed:
            return None
        df = pl.DataFrame(self._closed_rows).with_columns(
            pl.col("ts_ny").dt.replace_time_zone(NY.key),
        )
        return Bars(df=df, tf="1m", symbol=self.symbol)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="ICT live runner (Quantower bridge)")
    p.add_argument("--config", default=str(REPO_ROOT / "configs" / "lucid_propfirm.yaml"))
    p.add_argument("--dry-run", action="store_true",
                   help="No real orders even if config says otherwise.")
    p.add_argument("--confirm", default="",
                   help="Pass --confirm LIVE to enable real-order submission.")
    p.add_argument("--max-runtime-sec", type=int, default=0,
                   help="Stop after N seconds (0 = run until interrupted).")
    args = p.parse_args(argv)

    configure_logging()
    log = get_logger("scripts.run_live")
    cfg = _load_config(Path(args.config))
    log.info("config_loaded", path=args.config, account=cfg.get("account", {}).get("broker"))

    is_dry = args.dry_run or bool(cfg.get("execution", {}).get("dry_run", False))
    if not is_dry and args.confirm != "LIVE":
        log.error("safety_block",
                  msg="Live orders require --confirm LIVE (or set dry_run: true in config)")
        return 2

    conn = cfg["connection"]
    acct = cfg["account"]
    risk_cfg = cfg["risk"]
    exec_cfg = cfg["execution"]

    broker = QuantowerBroker(
        dom2_url=conn["dom2_url"],
        lucid_url=conn["lucid_url"],
        data_symbol=acct["data_symbol"],
        exec_symbol=acct["exec_symbol"],
        tick_size=0.25,
        tick_value_usd=0.50,
        qty_default=int(risk_cfg.get("max_quantity", 1)),
        dry_run=is_dry,
    )
    broker.connect()

    if not broker.feed.vivo(freshness_sec=10.0):
        log.error("preflight_failed", reason="dom2 feed not alive")
        broker.disconnect()
        return 3

    risk = RiskConfig(
        per_trade_risk_pct=float(risk_cfg["per_trade_risk_pct"]),
        max_quantity=int(risk_cfg["max_quantity"]),
        min_quantity=int(risk_cfg["min_quantity"]),
    )
    limits = LimitsConfig(
        daily_loss_limit_pct=float(risk_cfg["daily_loss_limit_pct"]),
        max_trades_per_day=int(risk_cfg["max_trades_per_day"]),
        max_consecutive_losses=int(risk_cfg["max_consecutive_losses"]),
    )
    instrument = InstrumentSpec(
        tick_size=0.25, tick_value_usd=0.50, point_value_usd=2.0,
    )
    live_cfg = LiveConfig(
        symbol=acct["exec_symbol"],
        starting_equity=float(exec_cfg["starting_equity_for_sizing"]),
        enforce_killzones=bool(exec_cfg["enforce_killzones"]),
        enforce_midnight_filter=bool(exec_cfg["enforce_midnight_filter"]),
        enforce_force_flat=bool(exec_cfg["enforce_force_flat"]),
    )
    kill = KillSwitch()
    runner = LiveRunner(
        broker=broker, config=live_cfg,
        instrument=instrument, risk=risk, limits=limits,
        kill_switch=kill,
    )

    # Telegram: notifier (fire-and-forget) + commander (long-poll listener).
    notifier = TelegramNotifier()
    commander = TelegramCommander(
        token=notifier.token, chat_id=notifier.chat_id,
        enabled=notifier.activo, poll_timeout=20,
    )
    commander.start()
    notifier.enviar(
        "sistema_inicio",
        f"ict_x_claude live ({acct['exec_symbol']}) — dry_run={is_dry}",
    )

    aggregator = _BarAggregator(
        symbol=acct["exec_symbol"],
        window_minutes=int(conn["bar_window_minutes"]),
    )
    poll_period = 1.0 / max(1, int(conn.get("poll_hz", 2)))

    def _graceful(_sig, _frame) -> None:
        log.warning("signal_received_flatten")
        notifier.enviar("sistema_parada", "SIGINT received — flatten + disconnect")
        kill.trip("manual_signal")
        broker.flatten_all()
        commander.stop()
        broker.disconnect()
        sys.exit(0)

    os_signal.signal(os_signal.SIGINT, _graceful)

    def _handle_commands() -> bool:
        """Drain queue, mutate runner state, send notifier feedback.
        Returns True if the loop should exit (after /stop or /restart)."""
        for cmd in commander.poll_commands():
            if cmd in {"status", "start", "help"}:
                pos = broker.positions()
                status_msg = (
                    f"paused={runner.paused} kill={kill.tripped} "
                    f"open_positions={len(pos)} equity_est={broker.equity_usd():.2f}"
                )
                notifier.enviar("comando_ok", f"/status → {status_msg}")
                continue
            if cmd == "pause":
                runner.paused = True
                notifier.enviar("pause", "/pause → no new entries")
                continue
            if cmd == "resume":
                runner.paused = False
                notifier.enviar("resume", "/resume → entries re-enabled")
                continue
            if cmd == "flatten":
                broker.flatten_all()
                notifier.enviar("flatten", "/flatten → all positions closed")
                continue
            if cmd == "stop":
                notifier.enviar("sistema_parada", "/stop → clean shutdown")
                runner.stop_requested = True
                return True
            if cmd == "restart":
                # exit code 42 is the conventional supervisor restart signal
                notifier.enviar("sistema_parada", "/restart → exit 42")
                broker.flatten_all()
                commander.stop()
                broker.disconnect()
                sys.exit(42)
        return False

    log.info("live_loop_started", dry_run=is_dry, exec_symbol=acct["exec_symbol"])
    started_at = time.time()
    last_kz_log = 0.0
    try:
        while True:
            if args.max_runtime_sec and (time.time() - started_at) > args.max_runtime_sec:
                log.info("max_runtime_reached")
                break

            if _handle_commands() or runner.stop_requested:
                break

            snap = broker.latest_snapshot()
            if snap is None:
                time.sleep(poll_period)
                continue

            ts_ny = to_ny(datetime.fromtimestamp(snap.ts_recepcion))
            bars = aggregator.feed(ts_ny, snap.precio)
            if bars is not None:
                runner.on_bars_window(bars)

            # Heartbeat every 60 s (log + Telegram if active)
            now = time.time()
            if now - last_kz_log >= 60:
                pos = broker.positions()
                log.info("heartbeat", ts_ny=str(ts_ny),
                         price=snap.precio, bars=len(aggregator._closed_rows),
                         open_positions=len(pos),
                         paused=runner.paused, kill_tripped=kill.tripped)
                last_kz_log = now
    except Exception as e:
        log.error("loop_crashed", error=f"{type(e).__name__}: {e}")
        kill.trip("loop_crash")
        notifier.enviar("error", f"loop crashed: {type(e).__name__}: {e}")
        broker.flatten_all()
    finally:
        commander.stop()
        broker.disconnect()
        notifier.enviar("sistema_parada", "loop stopped, disconnect ok")
        log.info("live_loop_stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
