"""Event-driven backtest engine — bar-by-bar.

Inputs:
    - Bars (1m or whatever TF the setups were detected on)
    - List of Signals to evaluate (pre-computed by setup detectors)
    - Instrument spec, risk config, limits, sessions config

For each bar:
    1. Check force-flatten time → close all open positions at next bar open.
    2. Check SL/TP hits on open positions (intra-bar with the bar's [low, high]).
    3. Process pending Signals whose entry-price is touched this bar AND that
       pass all gates (killzone, news block, lunch, midnight-open filter,
       limits, daily lock).
    4. Record equity point.

Fill model (default `next_bar_open`):
    A Signal that gates pass at bar t is enqueued as a market order to be
    filled at bar t+1's open (most conservative, avoids look-ahead).

Slippage:
    `slippage_ticks` added to the entry against the trader, and to the exit
    when SL hits (the IPDA wicks slightly past the stop). TP fills are exact.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ict_bot.backtest.orders import (
    Fill,
    Order,
    OrderStatus,
    Position,
    PositionStatus,
)
from ict_bot.backtest.portfolio import Portfolio
from ict_bot.data.models import Bars
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
from ict_bot.signals.setups.base import Signal, TradeSide
from ict_bot.utils.logging import get_logger
from ict_bot.utils.tz import to_ny

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    starting_equity: float = 100_000.0
    fill_model: str = "next_bar_open"   # only one implemented in v1
    slippage_ticks: int = 1
    commission_per_side_usd: float = 1.25
    enforce_killzones: bool = True
    enforce_midnight_filter: bool = True
    enforce_force_flat: bool = True


@dataclass(slots=True)
class _PendingEntry:
    signal: Signal
    submit_index: int


@dataclass(slots=True)
class BacktestResult:
    portfolio: Portfolio
    config: BacktestConfig
    mid_opens_by_day: dict[str, float] = field(default_factory=dict)
    skipped_signals: int = 0
    reasons_skipped: dict[str, int] = field(default_factory=dict)


def _midnight_opens(bars: Bars) -> dict[str, float]:
    """Build a {YYYY-MM-DD: open price of 00:00 NY bar} map for the whole series."""
    out: dict[str, float] = {}
    if bars.empty:
        return out
    rows = bars.df.iter_rows(named=True)
    for r in rows:
        ts = to_ny(r["ts_ny"])
        if ts.time().hour == 0 and ts.time().minute == 0:
            out.setdefault(ts.date().isoformat(), float(r["open"]))
    return out


def run_backtest(  # noqa: PLR0912, PLR0915
    bars: Bars,
    signals: list[Signal],
    *,
    config: BacktestConfig | None = None,
    instrument: InstrumentSpec | None = None,
    risk: RiskConfig | None = None,
    limits: LimitsConfig | None = None,
    sessions: SessionsConfig | None = None,
) -> BacktestResult:
    cfg = config or BacktestConfig()
    spec = instrument or InstrumentSpec()
    rcfg = risk or RiskConfig()
    lcfg = limits or LimitsConfig()
    scfg = sessions or SessionsConfig()

    pf = Portfolio(starting_equity=cfg.starting_equity, equity=cfg.starting_equity)
    state = LimitsState()
    mid_opens = _midnight_opens(bars)

    # Index signals by their bar_index for O(1) lookup
    sigs_by_bar: dict[int, list[Signal]] = {}
    for s in signals:
        sigs_by_bar.setdefault(s.bar_index, []).append(s)

    pending: list[_PendingEntry] = []
    next_order_id = 1
    next_position_id = 1
    skipped = 0
    reasons: dict[str, int] = {}

    opens = bars.df.get_column("open").to_list()
    highs = bars.df.get_column("high").to_list()
    lows = bars.df.get_column("low").to_list()
    ts_ny_list = bars.df.get_column("ts_ny").to_list()
    m = len(opens)

    def _skip(reason: str) -> None:
        nonlocal skipped
        skipped += 1
        reasons[reason] = reasons.get(reason, 0) + 1

    for t in range(m):
        ts_ny = to_ny(ts_ny_list[t])
        day_key = ts_ny.date().isoformat()
        mid_open = mid_opens.get(day_key)

        # Day rollover for limits
        if state.current_day != ts_ny.date():
            state.reset_for_day(ts_ny.date(), pf.equity)

        # ── 1. Force-flatten ──
        if cfg.enforce_force_flat and force_flat(ts_ny_list[t], scfg):
            for pos_id in list(pf.open_positions):
                pf.close_position(
                    pos_id, exit_price=opens[t] if t < m else opens[-1],
                    exit_index=t, exit_ts_ny=ts_ny_list[t],
                    status=PositionStatus.CLOSED_FLAT,
                    tick_size=spec.tick_size, tick_value_usd=spec.tick_value_usd,
                    commission_per_side_usd=cfg.commission_per_side_usd,
                )
                state.register_trade(pf.trades[-1].pnl_usd, config=lcfg)

        # ── 2. SL/TP intra-bar checks on open positions ──
        for pos_id in list(pf.open_positions):
            pos = pf.open_positions[pos_id]
            sl, tp = pos.order.stop_loss, pos.order.take_profit
            hi, lo = highs[t], lows[t]
            slip = cfg.slippage_ticks * spec.tick_size
            if pos.quantity > 0:    # long
                # Conservative: if both SL and TP touched within the bar, SL wins
                if lo <= sl:
                    pf.close_position(
                        pos_id, exit_price=sl - slip, exit_index=t,
                        exit_ts_ny=ts_ny_list[t], status=PositionStatus.CLOSED_SL,
                        tick_size=spec.tick_size, tick_value_usd=spec.tick_value_usd,
                        commission_per_side_usd=cfg.commission_per_side_usd,
                    )
                    state.register_trade(pf.trades[-1].pnl_usd, config=lcfg)
                elif hi >= tp:
                    pf.close_position(
                        pos_id, exit_price=tp, exit_index=t,
                        exit_ts_ny=ts_ny_list[t], status=PositionStatus.CLOSED_TP,
                        tick_size=spec.tick_size, tick_value_usd=spec.tick_value_usd,
                        commission_per_side_usd=cfg.commission_per_side_usd,
                    )
                    state.register_trade(pf.trades[-1].pnl_usd, config=lcfg)
            elif hi >= sl:
                pf.close_position(
                    pos_id, exit_price=sl + slip, exit_index=t,
                    exit_ts_ny=ts_ny_list[t], status=PositionStatus.CLOSED_SL,
                    tick_size=spec.tick_size, tick_value_usd=spec.tick_value_usd,
                    commission_per_side_usd=cfg.commission_per_side_usd,
                )
                state.register_trade(pf.trades[-1].pnl_usd, config=lcfg)
            elif lo <= tp:
                pf.close_position(
                    pos_id, exit_price=tp, exit_index=t,
                    exit_ts_ny=ts_ny_list[t], status=PositionStatus.CLOSED_TP,
                    tick_size=spec.tick_size, tick_value_usd=spec.tick_value_usd,
                    commission_per_side_usd=cfg.commission_per_side_usd,
                )
                state.register_trade(pf.trades[-1].pnl_usd, config=lcfg)

        # ── 3. Fill pending entries enqueued on the previous bar ──
        if pending:
            still: list[_PendingEntry] = []
            for pe in pending:
                # Fill at this bar's open (next_bar_open model)
                if pe.submit_index >= t:
                    still.append(pe)
                    continue
                s = pe.signal
                fill_price = opens[t]
                # Skip if fill price is already past SL (gapped beyond)
                if (s.side == TradeSide.BUY and fill_price <= s.stop_loss) or \
                   (s.side == TradeSide.SELL and fill_price >= s.stop_loss):
                    _skip("gap_past_sl")
                    continue
                qty = size_position(
                    pf.equity, fill_price, s.stop_loss,
                    instrument=spec, risk=rcfg,
                )
                if qty == 0:
                    _skip("sizing_zero")
                    continue
                signed_qty = qty if s.side == TradeSide.BUY else -qty
                order = Order(
                    order_id=next_order_id,
                    setup_name=s.setup_name,
                    side=str(s.side),
                    entry_price=s.entry_price,
                    stop_loss=s.stop_loss,
                    take_profit=s.take_profit,
                    quantity=qty,
                    submitted_at_index=pe.submit_index,
                    submitted_ts_ny=ts_ny_list[pe.submit_index],
                    status=OrderStatus.FILLED,
                )
                next_order_id += 1
                fill = Fill(
                    order_id=order.order_id,
                    fill_price=fill_price,
                    fill_index=t,
                    fill_ts_ny=ts_ny_list[t],
                    commission_usd=cfg.commission_per_side_usd * qty,
                    slippage_ticks=cfg.slippage_ticks,
                )
                pos = Position(
                    position_id=next_position_id,
                    order=order,
                    fill=fill,
                    quantity=signed_qty,
                )
                pf.open_positions[next_position_id] = pos
                next_position_id += 1
            pending = still

        # ── 4. Process today's signals (enqueue for next-bar open) ──
        for s in sigs_by_bar.get(t, []):
            if not state.can_trade(config=lcfg):
                _skip("limits_lock")
                continue
            if cfg.enforce_killzones and not new_entries_allowed(ts_ny_list[t], scfg):
                _skip("outside_gate")
                continue
            if cfg.enforce_midnight_filter and (
                (s.side == TradeSide.BUY
                 and not midnight_open_filter_long(s.entry_price, mid_open))
                or (s.side == TradeSide.SELL
                    and not midnight_open_filter_short(s.entry_price, mid_open))
            ):
                _skip("mid_open_filter")
                continue
            # Only one open position at a time (v1)
            if pf.open_positions:
                _skip("position_already_open")
                continue
            pending.append(_PendingEntry(signal=s, submit_index=t))

        pf.record_equity_point(ts_ny_list[t])

    # Final flatten
    if pf.open_positions:
        last_t = m - 1
        last_open = opens[last_t]
        for pos_id in list(pf.open_positions):
            pf.close_position(
                pos_id, exit_price=last_open, exit_index=last_t,
                exit_ts_ny=ts_ny_list[last_t],
                status=PositionStatus.CLOSED_FLAT,
                tick_size=spec.tick_size, tick_value_usd=spec.tick_value_usd,
                commission_per_side_usd=cfg.commission_per_side_usd,
            )

    log.info(
        "backtest_done",
        trades=len(pf.trades),
        final_equity=pf.equity,
        skipped=skipped,
        reasons=reasons,
    )
    return BacktestResult(
        portfolio=pf, config=cfg,
        mid_opens_by_day=mid_opens,
        skipped_signals=skipped,
        reasons_skipped=reasons,
    )
