"""PILOT 009 — MGC-specific threshold sensitivity sweep.

Pilot 008 showed gold has its own edge profile distinct from NQ. This
sweep searches for gold's OWN plateau (not NQ's), independent of the
production cell.

Grid (12 cells):
    body_atr_min ∈ (0.8, 1.0, 1.25, 1.5)
    fixed_tp_r   ∈ (1.5, 2.0, 2.5)
    body_range_min held at 0.5 (NQ plateau center; unlikely to be the
        gold optimum but holding 1 dim fixed makes the result readable)

Operates strictly in shadow: this script does NOT touch
`configs/lucid_propfirm.yaml` or any production code. The NQ live
configuration for tomorrow's session stays untouched. Outputs land in
`reports/pilots/pilot_009_*/` and a docs/pilots/009_*.md is written
after the run.
"""

from __future__ import annotations

import io
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from statistics import fmean

from ict_bot.backtest.engine import BacktestConfig, run_backtest
from ict_bot.backtest.runner import PipelineConfig, detect_all_signals
from ict_bot.config.settings import REPO_ROOT
from ict_bot.data.loaders.cme_csv import load_cme_csv
from ict_bot.reporting.metrics import compute_metrics
from ict_bot.risk.sizing import InstrumentSpec
from ict_bot.sessions.killzones import SessionsConfig
from ict_bot.signals.imbalance.fvg import FVGConfig
from ict_bot.signals.setups.mss_fvg import MssFvgConfig
from ict_bot.signals.setups.ob_ote import ObOteConfig
from ict_bot.signals.setups.silver_bullet import SilverBulletConfig
from ict_bot.signals.setups.unicorn import UnicornConfig
from ict_bot.structure.displacement import DisplacementConfig
from ict_bot.utils.logging import configure_logging, get_logger

if isinstance(sys.stdout, io.TextIOWrapper):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]


MGC_SPEC = InstrumentSpec(tick_size=0.10, tick_value_usd=1.00, point_value_usd=10.0)

BODY_ATR_GRID: tuple[float, ...] = (0.8, 1.0, 1.25, 1.5)
FIXED_TP_GRID: tuple[float, ...] = (1.5, 2.0, 2.5)
BODY_RANGE_FIXED: float = 0.5


@dataclass(frozen=True, slots=True)
class Cell:
    body_atr: float
    body_range: float
    fixed_tp_r: float


@dataclass(slots=True)
class CellResult:
    cell: Cell
    n_trades: int
    win_rate: float
    expectancy_r: float
    expectancy_usd: float
    pnl_usd: float
    max_dd_pct: float
    worst_trade_usd: float
    max_consec_losers: int
    mean_sl_pts: float
    mean_sl_usd: float
    score: float  # tr/day × exp_r, the metric to maximise
    extra: dict[str, float] = field(default_factory=dict)


def _max_consec_losses(trades: list) -> int:
    streak = 0
    worst = 0
    for t in sorted(trades, key=lambda x: x.entry_ts_ny):
        if t.pnl_usd < 0:
            streak += 1
            worst = max(worst, streak)
        else:
            streak = 0
    return worst


def _run_cell(bars, cell: Cell, n_days: int, log) -> CellResult:
    t0 = time.time()
    pcfg = PipelineConfig(
        displacement=DisplacementConfig(
            atr_lookback=14,
            body_atr_min=cell.body_atr,
            body_range_min=cell.body_range,
        ),
        fvg=FVGConfig(require_displacement=True, min_gap_ticks=1, tick_size=0.10),
        unicorn=UnicornConfig(
            min_rr=1.0, tp_strategy="fixed_R", fixed_tp_r=cell.fixed_tp_r,
        ),
        mss_fvg=MssFvgConfig(
            min_rr=1.0, tp_strategy="fixed_R", fixed_tp_r=cell.fixed_tp_r,
        ),
        ob_ote=ObOteConfig(
            min_rr=1.0, tp_strategy="fixed_R", fixed_tp_r=cell.fixed_tp_r,
        ),
        silver_bullet=SilverBulletConfig(
            min_rr=1.0, tp_strategy="fixed_R", fixed_tp_r=cell.fixed_tp_r,
        ),
    )
    sess = SessionsConfig(allowed_windows=("silver_bullet_am", "silver_bullet_pm"))
    bcfg = BacktestConfig(enforce_killzones=True, enforce_midnight_filter=True)

    signals = detect_all_signals(bars, cfg=pcfg)
    result = run_backtest(bars, signals, config=bcfg, sessions=sess,
                          instrument=MGC_SPEC)
    m = compute_metrics(result.portfolio)
    sls = [abs(t.entry_price - t.stop_loss) for t in result.portfolio.trades]
    sl_usd = [d * MGC_SPEC.point_value_usd for d in sls]
    score = round((m.n_trades / max(1, n_days)) * m.expectancy_r, 4)
    log.info("cell_done",
             body_atr=cell.body_atr, body_range=cell.body_range,
             fixed_tp_r=cell.fixed_tp_r, trades=m.n_trades,
             exp_r=round(m.expectancy_r, 3), score=score,
             elapsed_s=round(time.time() - t0, 1))
    return CellResult(
        cell=cell,
        n_trades=m.n_trades,
        win_rate=round(m.win_rate, 3),
        expectancy_r=round(m.expectancy_r, 3),
        expectancy_usd=round(m.expectancy_usd, 2),
        pnl_usd=round(m.total_pnl_usd, 2),
        max_dd_pct=round(m.max_drawdown_pct, 4),
        worst_trade_usd=round(
            min((t.pnl_usd for t in result.portfolio.trades), default=0.0), 2,
        ),
        max_consec_losers=_max_consec_losses(result.portfolio.trades),
        mean_sl_pts=round(fmean(sls), 3) if sls else 0.0,
        mean_sl_usd=round(fmean(sl_usd), 2) if sl_usd else 0.0,
        score=score,
        extra={"trades_per_day": round(m.n_trades / max(1, n_days), 3)},
    )


def main() -> int:
    configure_logging()
    log = get_logger("pilot.009")
    log.info("loading_mgc")
    bars = load_cme_csv(
        REPO_ROOT / "data" / "cme_mcg_2021_2026" /
        "glbx-mdp3-20210325-20260621.ohlcv-1m (1).csv",
        family="MGC", start=date(2025, 1, 1),
    )
    n_days = max(1, (bars.last_ts() - bars.first_ts()).days)  # type: ignore[operator]
    log.info("mgc_ready", bars=len(bars), n_days=n_days)

    results: list[CellResult] = []
    grid = [
        Cell(atr, BODY_RANGE_FIXED, tp)
        for atr in BODY_ATR_GRID
        for tp in FIXED_TP_GRID
    ]
    log.info("sweep_start", n_cells=len(grid))
    for i, c in enumerate(grid, 1):
        log.info("cell_start", i=i, total=len(grid),
                 body_atr=c.body_atr, fixed_tp_r=c.fixed_tp_r)
        results.append(_run_cell(bars, c, n_days, log))

    # Rank by score (tr/day * exp_r)
    results.sort(key=lambda r: r.score, reverse=True)

    run_id = datetime.now().strftime("%Y%m%dT%H%M%S")
    out_dir = REPO_ROOT / "reports" / "pilots" / f"pilot_009_{run_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(json.dumps(
        [
            {
                "body_atr_min": r.cell.body_atr,
                "body_range_min": r.cell.body_range,
                "fixed_tp_r": r.cell.fixed_tp_r,
                "n_trades": r.n_trades,
                "trades_per_day": r.extra["trades_per_day"],
                "win_rate": r.win_rate,
                "expectancy_r": r.expectancy_r,
                "expectancy_usd": r.expectancy_usd,
                "pnl_usd": r.pnl_usd,
                "max_dd_pct": r.max_dd_pct,
                "worst_trade_usd": r.worst_trade_usd,
                "max_consec_losers": r.max_consec_losers,
                "mean_sl_pts": r.mean_sl_pts,
                "mean_sl_usd": r.mean_sl_usd,
                "score": r.score,
            }
            for r in results
        ],
        indent=2, default=str,
    ))

    print("\n=== PILOT 009 — MGC sensitivity sweep "
          f"({len(grid)} cells, body_range fixed at {BODY_RANGE_FIXED}) ===\n")
    print(f"{'atr':<5} {'tp_r':<5} {'trades':<7} {'tr/d':<5} {'WR':<6} "
          f"{'exp R':<7} {'PnL':<11} {'MaxDD':<7} {'consec L':<9} "
          f"{'SL$/ct':<7} {'score':<7}")
    print("-" * 90)
    for r in results:
        print(
            f"{r.cell.body_atr:<5.2f} {r.cell.fixed_tp_r:<5.2f} "
            f"{r.n_trades:<7} {r.extra['trades_per_day']:<5.2f} "
            f"{r.win_rate:<6.0%} {r.expectancy_r:<+7.2f} "
            f"${r.pnl_usd:<10,.0f} {r.max_dd_pct:<6.2%} "
            f"{r.max_consec_losers:<9} ${r.mean_sl_usd:<6.0f} "
            f"{r.score:<+7.3f}",
        )
    print(f"\nArtifacts: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
