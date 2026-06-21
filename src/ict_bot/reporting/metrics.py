"""Performance metrics for a completed backtest."""

from __future__ import annotations

import math
from dataclasses import dataclass

from ict_bot.backtest.portfolio import Portfolio


@dataclass(frozen=True, slots=True)
class Metrics:
    n_trades: int
    n_wins: int
    n_losses: int
    win_rate: float
    avg_win_usd: float
    avg_loss_usd: float
    profit_factor: float
    expectancy_usd: float
    expectancy_r: float
    total_pnl_usd: float
    final_equity: float
    starting_equity: float
    max_drawdown_usd: float
    max_drawdown_pct: float
    sharpe: float        # annualized over trades (not time)
    sortino: float


def _max_drawdown(equity_series: list[float]) -> tuple[float, float]:
    if not equity_series:
        return 0.0, 0.0
    peak = equity_series[0]
    max_dd = 0.0
    max_dd_pct = 0.0
    for e in equity_series:
        peak = max(peak, e)
        dd = peak - e
        dd_pct = dd / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd
            max_dd_pct = dd_pct
    return max_dd, max_dd_pct


def compute_metrics(pf: Portfolio) -> Metrics:
    pnls = [t.pnl_usd for t in pf.trades]
    rs = [t.r_multiple for t in pf.trades]
    n = len(pnls)
    if n == 0:
        return Metrics(
            n_trades=0, n_wins=0, n_losses=0, win_rate=0.0,
            avg_win_usd=0.0, avg_loss_usd=0.0,
            profit_factor=0.0, expectancy_usd=0.0, expectancy_r=0.0,
            total_pnl_usd=0.0, final_equity=pf.equity,
            starting_equity=pf.starting_equity,
            max_drawdown_usd=0.0, max_drawdown_pct=0.0,
            sharpe=0.0, sortino=0.0,
        )
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0
    win_rate = len(wins) / n
    gross_win = sum(wins)
    gross_loss = -sum(losses)
    pf_metric = gross_win / gross_loss if gross_loss > 0 else float("inf")
    expectancy_usd = sum(pnls) / n
    expectancy_r = sum(rs) / n
    total_pnl = sum(pnls)
    equity_track = [pf.starting_equity]
    for p in pnls:
        equity_track.append(equity_track[-1] + p)
    dd_usd, dd_pct = _max_drawdown(equity_track)
    mean_r = sum(rs) / n if n > 0 else 0.0
    std_r = math.sqrt(sum((x - mean_r) ** 2 for x in rs) / n) if n > 0 else 0.0
    downside = [x for x in rs if x < 0]
    if downside:
        ds_var = sum(x ** 2 for x in downside) / len(downside)
        ds_std = math.sqrt(ds_var)
    else:
        ds_std = 0.0
    sharpe = (mean_r / std_r * math.sqrt(n)) if std_r > 0 else 0.0
    sortino = (mean_r / ds_std * math.sqrt(n)) if ds_std > 0 else 0.0
    return Metrics(
        n_trades=n, n_wins=len(wins), n_losses=len(losses), win_rate=win_rate,
        avg_win_usd=avg_win, avg_loss_usd=avg_loss,
        profit_factor=pf_metric,
        expectancy_usd=expectancy_usd, expectancy_r=expectancy_r,
        total_pnl_usd=total_pnl,
        final_equity=pf.equity, starting_equity=pf.starting_equity,
        max_drawdown_usd=dd_usd, max_drawdown_pct=dd_pct,
        sharpe=sharpe, sortino=sortino,
    )


def format_metrics(m: Metrics) -> str:
    return (
        f"Trades: {m.n_trades}  Wins: {m.n_wins}  Losses: {m.n_losses}  "
        f"WinRate: {m.win_rate:.1%}\n"
        f"AvgWin: ${m.avg_win_usd:,.2f}  AvgLoss: ${m.avg_loss_usd:,.2f}  "
        f"PF: {m.profit_factor:.2f}\n"
        f"Expectancy: ${m.expectancy_usd:,.2f} / {m.expectancy_r:+.2f}R  "
        f"Total PnL: ${m.total_pnl_usd:,.2f}\n"
        f"Equity: ${m.starting_equity:,.0f} -> ${m.final_equity:,.2f}\n"
        f"MaxDD: ${m.max_drawdown_usd:,.2f} ({m.max_drawdown_pct:.1%})\n"
        f"Sharpe(per-trade, annualized-by-N): {m.sharpe:.2f}  Sortino: {m.sortino:.2f}"
    )
