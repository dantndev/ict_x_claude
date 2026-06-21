"""PILOT 005 — Compare session-filter modes with WF + worst-case analysis.

Three modes, all on the winner cell (body_atr=1.0, body_range=0.5,
fixed_tp_r=1.5, tp_strategy=fixed_R):

    A_all_kz        : default (all KZ + silver-bullet windows)
    C_ny_plus_sb    : ny_am_kz, ny_pm_kz, silver_bullet_am, silver_bullet_pm
    B_silver_only   : silver_bullet_am, silver_bullet_pm

For each mode reports:
- WF 8 folds: aggregate exp R, PnL, folds positive
- Worst fold (lowest PnL)
- Full-period: trades, WR, PnL, MaxDD, Sharpe
- Worst single trade, max consecutive losses, worst calendar month
- Bootstrap 1000 iter: mean/p95 max DD, prob_profitable

So the user can decide B vs C based on real worst-case metrics.
"""

from __future__ import annotations

import io
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime

from ict_bot.backtest.engine import BacktestConfig
from ict_bot.backtest.runner import PipelineConfig
from ict_bot.config.settings import REPO_ROOT
from ict_bot.data.loaders.cme_csv import load_cme_csv
from ict_bot.data.resampler import resample
from ict_bot.reporting.metrics import compute_metrics
from ict_bot.sessions.killzones import SessionsConfig
from ict_bot.signals.imbalance.fvg import FVGConfig
from ict_bot.signals.setups.mss_fvg import MssFvgConfig
from ict_bot.signals.setups.ob_ote import ObOteConfig
from ict_bot.signals.setups.silver_bullet import SilverBulletConfig
from ict_bot.signals.setups.unicorn import UnicornConfig
from ict_bot.structure.displacement import DisplacementConfig
from ict_bot.utils.logging import configure_logging, get_logger
from ict_bot.validation.bootstrap import bootstrap_stats
from ict_bot.validation.walk_forward import walk_forward

if isinstance(sys.stdout, io.TextIOWrapper):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]


WINNER = {"body_atr_min": 1.0, "body_range_min": 0.5, "fixed_tp_r": 1.5}


@dataclass(frozen=True, slots=True)
class Mode:
    name: str
    description: str
    allowed_windows: tuple[str, ...] | None


MODES: tuple[Mode, ...] = (
    Mode("A_all_kz", "All killzones + Silver Bullet (current default)", None),
    Mode("C_ny_plus_sb", "NY AM/PM + Silver Bullet (no London)",
         ("ny_am_kz", "ny_pm_kz", "silver_bullet_am", "silver_bullet_pm")),
    Mode("B_silver_only", "Silver Bullet AM + PM only",
         ("silver_bullet_am", "silver_bullet_pm")),
)


def _build_pcfg() -> PipelineConfig:
    return PipelineConfig(
        displacement=DisplacementConfig(
            atr_lookback=14,
            body_atr_min=WINNER["body_atr_min"],
            body_range_min=WINNER["body_range_min"],
        ),
        fvg=FVGConfig(require_displacement=True, min_gap_ticks=1, tick_size=0.25),
        unicorn=UnicornConfig(min_rr=1.0, tp_strategy="fixed_R",
                               fixed_tp_r=WINNER["fixed_tp_r"]),
        mss_fvg=MssFvgConfig(min_rr=1.0, tp_strategy="fixed_R",
                              fixed_tp_r=WINNER["fixed_tp_r"]),
        ob_ote=ObOteConfig(min_rr=1.0, tp_strategy="fixed_R",
                            fixed_tp_r=WINNER["fixed_tp_r"]),
        silver_bullet=SilverBulletConfig(min_rr=1.0, tp_strategy="fixed_R",
                                          fixed_tp_r=WINNER["fixed_tp_r"]),
    )


def _worst_month(trades: list) -> tuple[str, float, int]:
    """Return (year-month, pnl, n_trades) of the worst calendar month."""
    by_month: dict[str, list[float]] = defaultdict(list)
    for t in trades:
        key = t.entry_ts_ny.strftime("%Y-%m")
        by_month[key].append(t.pnl_usd)
    if not by_month:
        return ("n/a", 0.0, 0)
    sums = [(k, sum(v), len(v)) for k, v in by_month.items()]
    return min(sums, key=lambda x: x[1])


def _max_consecutive_losses(trades: list) -> int:
    streak = 0
    worst = 0
    for t in sorted(trades, key=lambda x: x.entry_ts_ny):
        if t.pnl_usd < 0:
            streak += 1
            worst = max(worst, streak)
        else:
            streak = 0
    return worst


def main() -> int:
    configure_logging()
    log = get_logger("pilot.005")

    bars_1m = load_cme_csv(
        REPO_ROOT / "data" / "cme_nq_2021_2026" / "datos_cme.csv",
        family="MNQ", start=date(2024, 1, 1),
    )
    bars = resample(bars_1m, "5m")
    log.info("bars_ready", tf=bars.tf, bars=len(bars))

    pcfg = _build_pcfg()
    rows: list[dict] = []

    for mode in MODES:
        log.info("mode_start", name=mode.name)
        sess = SessionsConfig(allowed_windows=mode.allowed_windows)
        bcfg = BacktestConfig(enforce_killzones=True, enforce_midnight_filter=True)

        # WF 8 folds
        wf = walk_forward(
            bars, n_folds=8, train_ratio=0.7, embargo_bars=60,
            pipeline_config=pcfg, backtest_config=bcfg,
        )
        wf_per_fold = [
            {
                "fold": f.fold_index,
                "trades": f.metrics.n_trades,
                "exp_r": round(f.metrics.expectancy_r, 3),
                "pnl_usd": round(f.metrics.total_pnl_usd, 2),
                "wr": round(f.metrics.win_rate, 3),
            }
            for f in wf.folds
        ]
        worst_fold = (
            min(wf_per_fold, key=lambda x: x["pnl_usd"])
            if wf_per_fold else None
        )

        # Full period with the session-filtered config — bypass run_pipeline
        # because the runner doesn't take SessionsConfig directly.
        from ict_bot.backtest.engine import run_backtest as _run
        from ict_bot.backtest.runner import detect_all_signals as _detect
        signals = _detect(bars, cfg=pcfg)
        result = _run(bars, signals, config=bcfg, sessions=sess)
        full_m = compute_metrics(result.portfolio)
        boot = bootstrap_stats(result.portfolio, iterations=1000)

        worst_trade_pnl = (
            min(t.pnl_usd for t in result.portfolio.trades)
            if result.portfolio.trades else 0.0
        )
        max_consec = _max_consecutive_losses(result.portfolio.trades)
        wm_key, wm_pnl, wm_n = _worst_month(result.portfolio.trades)

        rows.append({
            "mode": mode.name,
            "description": mode.description,
            "allowed_windows": list(mode.allowed_windows) if mode.allowed_windows else "all",
            "wf_folds_positive": sum(1 for f in wf.folds if f.metrics.expectancy_r > 0),
            "wf_n_folds": wf.n_folds,
            "wf_aggregate_exp_r": round(wf.aggregate_expectancy_r(), 3),
            "wf_aggregate_pnl_usd": round(wf.aggregate_total_pnl(), 2),
            "wf_worst_fold": worst_fold,
            "wf_per_fold": wf_per_fold,
            "full_trades": full_m.n_trades,
            "full_win_rate": round(full_m.win_rate, 3),
            "full_exp_r": round(full_m.expectancy_r, 3),
            "full_pnl_usd": round(full_m.total_pnl_usd, 2),
            "full_max_dd_usd": round(full_m.max_drawdown_usd, 2),
            "full_max_dd_pct": round(full_m.max_drawdown_pct, 4),
            "full_sharpe": round(full_m.sharpe, 2),
            "worst_single_trade_usd": round(worst_trade_pnl, 2),
            "max_consecutive_losses": max_consec,
            "worst_month": wm_key,
            "worst_month_pnl_usd": round(wm_pnl, 2),
            "worst_month_n_trades": wm_n,
            "boot_max_dd_mean_pct": round(boot.max_dd_mean_pct, 4),
            "boot_max_dd_p95_pct": round(boot.max_dd_p95_pct, 4),
            "boot_prob_profitable": round(boot.prob_profitable, 3),
        })
        log.info("mode_done", name=mode.name, full_trades=full_m.n_trades,
                 full_pnl=full_m.total_pnl_usd, full_exp_r=full_m.expectancy_r)

    run_id = datetime.now().strftime("%Y%m%dT%H%M%S")
    out_dir = REPO_ROOT / "reports" / "pilots" / f"pilot_005_{run_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(json.dumps(rows, indent=2, default=str))

    # Print compact comparison
    print("\n=== PILOT 005 — Session mode comparison ===\n")
    print(f"Cell: body_atr={WINNER['body_atr_min']}, body_range={WINNER['body_range_min']}, "
          f"fixed_tp_r={WINNER['fixed_tp_r']}, tp_strategy=fixed_R\n")
    print(f"{'mode':<15} {'trades':>8} {'WR':>6} {'exp R':>7} "
          f"{'PnL':>12} {'MaxDD':>10} {'p95 DD':>8} "
          f"{'WF agg R':>9} {'WF folds':>9} {'worst trade':>12} "
          f"{'max losers':>11} {'worst month':>22}")
    print("-" * 175)
    for r in rows:
        wm_pnl = r["worst_month_pnl_usd"]
        wm_n = r["worst_month_n_trades"]
        wm_label = f"{r['worst_month']} ({wm_n} tr ${wm_pnl:,.0f})"
        folds_label = f"{r['wf_folds_positive']}/{r['wf_n_folds']}"
        print(
            f"{r['mode']:<15} "
            f"{r['full_trades']:>8} {r['full_win_rate']:>6.0%} "
            f"{r['full_exp_r']:>+7.2f} ${r['full_pnl_usd']:>10,.0f} "
            f"{r['full_max_dd_pct']:>9.2%} {r['boot_max_dd_p95_pct']:>7.2%} "
            f"{r['wf_aggregate_exp_r']:>+9.2f} "
            f"{folds_label:>9} "
            f"${r['worst_single_trade_usd']:>10,.0f} "
            f"{r['max_consecutive_losses']:>11} "
            f"{wm_label:>22}",
        )

    print(f"\nArtifacts: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
