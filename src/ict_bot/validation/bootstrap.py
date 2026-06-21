"""Monte Carlo bootstrap of the trade-PnL sequence to estimate edge stability."""

from __future__ import annotations

import random
import statistics
from dataclasses import dataclass

from ict_bot.backtest.portfolio import Portfolio


@dataclass(frozen=True, slots=True)
class BootstrapStats:
    n_iterations: int
    final_equity_mean: float
    final_equity_p05: float
    final_equity_p95: float
    max_dd_mean_pct: float
    max_dd_p95_pct: float
    prob_profitable: float


def _max_dd_pct(seq: list[float]) -> float:
    if not seq:
        return 0.0
    peak = seq[0]
    worst = 0.0
    for v in seq:
        peak = max(peak, v)
        if peak > 0:
            worst = max(worst, (peak - v) / peak)
    return worst


def bootstrap_equity(
    pnls: list[float],
    *,
    starting_equity: float,
    iterations: int = 1000,
    seed: int | None = 42,
) -> list[list[float]]:
    """Return `iterations` synthetic equity curves by shuffling trade order."""
    rng = random.Random(seed)
    out: list[list[float]] = []
    for _ in range(iterations):
        order = pnls.copy()
        rng.shuffle(order)
        eq = [starting_equity]
        for p in order:
            eq.append(eq[-1] + p)
        out.append(eq)
    return out


def bootstrap_stats(pf: Portfolio, *, iterations: int = 1000,
                    seed: int | None = 42) -> BootstrapStats:
    pnls = [t.pnl_usd for t in pf.trades]
    if not pnls:
        return BootstrapStats(0, pf.equity, pf.equity, pf.equity, 0.0, 0.0, 0.0)
    curves = bootstrap_equity(pnls, starting_equity=pf.starting_equity,
                              iterations=iterations, seed=seed)
    finals = [c[-1] for c in curves]
    dds = [_max_dd_pct(c) for c in curves]
    finals_sorted = sorted(finals)
    p05 = finals_sorted[int(0.05 * iterations)]
    p95 = finals_sorted[int(0.95 * iterations)]
    dds_sorted = sorted(dds)
    dd_p95 = dds_sorted[int(0.95 * iterations)]
    prob_profitable = sum(1 for f in finals if f > pf.starting_equity) / iterations
    return BootstrapStats(
        n_iterations=iterations,
        final_equity_mean=statistics.fmean(finals),
        final_equity_p05=p05,
        final_equity_p95=p95,
        max_dd_mean_pct=statistics.fmean(dds),
        max_dd_p95_pct=dd_p95,
        prob_profitable=prob_profitable,
    )
