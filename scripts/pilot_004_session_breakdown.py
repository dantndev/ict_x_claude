"""PILOT 004 — Re-WF the winner with limits bugfix + per-killzone breakdown.

Runs walk_forward + full-period + bootstrap for the pilot-003 winner cell
`(body_atr=1.0, body_range=0.5, fixed_tp_r=1.5, tp_strategy=fixed_R)` now
that the LimitsState.reset_for_day bug is fixed.

Then groups every trade in the full-period run by the killzone the entry
fell into, so we can answer "where does the edge come from?" — London,
NY AM, NY PM, Silver Bullet windows, or outside.

Outputs under reports/pilots/pilot_004_<run_id>/.
"""

from __future__ import annotations

import io
import json
import sys
from collections import defaultdict
from datetime import date, datetime
from statistics import fmean

import polars as pl

from ict_bot.backtest.engine import BacktestConfig
from ict_bot.backtest.runner import PipelineConfig, run_pipeline
from ict_bot.config.settings import REPO_ROOT
from ict_bot.data.loaders.cme_csv import load_cme_csv
from ict_bot.data.resampler import resample
from ict_bot.reporting.metrics import compute_metrics
from ict_bot.sessions.killzones import SessionsConfig
from ict_bot.sessions.sessions import session_tag_at
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


WINNER = {
    "body_atr_min": 1.0,
    "body_range_min": 0.5,
    "fixed_tp_r": 1.5,
}


def _build_pcfg() -> PipelineConfig:
    return PipelineConfig(
        displacement=DisplacementConfig(
            atr_lookback=14,
            body_atr_min=WINNER["body_atr_min"],
            body_range_min=WINNER["body_range_min"],
        ),
        fvg=FVGConfig(require_displacement=True, min_gap_ticks=1, tick_size=0.25),
        unicorn=UnicornConfig(
            min_rr=1.0, tp_strategy="fixed_R", fixed_tp_r=WINNER["fixed_tp_r"],
        ),
        mss_fvg=MssFvgConfig(
            min_rr=1.0, tp_strategy="fixed_R", fixed_tp_r=WINNER["fixed_tp_r"],
        ),
        ob_ote=ObOteConfig(
            min_rr=1.0, tp_strategy="fixed_R", fixed_tp_r=WINNER["fixed_tp_r"],
        ),
        silver_bullet=SilverBulletConfig(
            min_rr=1.0, tp_strategy="fixed_R", fixed_tp_r=WINNER["fixed_tp_r"],
        ),
    )


def main() -> int:
    configure_logging()
    log = get_logger("pilot.004")

    bars_1m = load_cme_csv(
        REPO_ROOT / "data" / "cme_nq_2021_2026" / "datos_cme.csv",
        family="MNQ", start=date(2024, 1, 1),
    )
    bars = resample(bars_1m, "5m")
    log.info("bars_ready", tf=bars.tf, bars=len(bars))

    pcfg = _build_pcfg()
    bcfg = BacktestConfig(enforce_killzones=True, enforce_midnight_filter=True)
    sess_cfg = SessionsConfig()

    # 1. Walk-forward 8 folds for the OOS edge metric
    log.info("walk_forward_start")
    wf = walk_forward(
        bars, n_folds=8, train_ratio=0.7, embargo_bars=60,
        pipeline_config=pcfg, backtest_config=bcfg,
    )
    wf_per_fold = [
        {
            "fold": f.fold_index,
            "n_trades": f.metrics.n_trades,
            "exp_r": round(f.metrics.expectancy_r, 3),
            "pnl_usd": round(f.metrics.total_pnl_usd, 2),
            "win_rate": round(f.metrics.win_rate, 3),
        }
        for f in wf.folds
    ]

    # 2. Full-period for clean bootstrap (now with limits bug fixed)
    log.info("full_period_start")
    full = run_pipeline(bars, pipeline_config=pcfg, backtest_config=bcfg)
    full_m = compute_metrics(full.portfolio)
    boot = bootstrap_stats(full.portfolio, iterations=1000)

    # 3. Per-killzone breakdown of trades
    bucket: dict[str, list[dict]] = defaultdict(list)
    for t in full.portfolio.trades:
        tag = session_tag_at(t.entry_ts_ny, sess_cfg)
        bucket[tag].append({
            "pnl_usd": t.pnl_usd, "r": t.r_multiple,
            "side": t.side, "win": t.pnl_usd > 0,
        })

    session_stats = {}
    for tag, trades in sorted(bucket.items()):
        n = len(trades)
        wins = sum(1 for t in trades if t["win"])
        pnls = [t["pnl_usd"] for t in trades]
        rs = [t["r"] for t in trades]
        session_stats[tag] = {
            "n_trades": n,
            "win_rate": round(wins / n, 3) if n else 0.0,
            "expectancy_r": round(fmean(rs), 3) if rs else 0.0,
            "expectancy_usd": round(fmean(pnls), 2) if pnls else 0.0,
            "total_pnl_usd": round(sum(pnls), 2),
            "share_of_trades_pct": round(100 * n / max(1, full_m.n_trades), 1),
            "share_of_pnl_pct": round(100 * sum(pnls) / max(1, full_m.total_pnl_usd), 1)
            if full_m.total_pnl_usd != 0 else 0.0,
        }

    # Persist
    run_id = datetime.now().strftime("%Y%m%dT%H%M%S")
    out_dir = REPO_ROOT / "reports" / "pilots" / f"pilot_004_{run_id}"
    out_dir.mkdir(parents=True, exist_ok=True)

    report = {
        "winner_cell": WINNER,
        "range": {"from": "2024-01-01", "to": str(bars.last_ts())},
        "wf_aggregate_exp_r": round(wf.aggregate_expectancy_r(), 3),
        "wf_aggregate_pnl_usd": round(wf.aggregate_total_pnl(), 2),
        "wf_folds_positive": sum(1 for f in wf.folds if f.metrics.expectancy_r > 0),
        "wf_n_folds": wf.n_folds,
        "wf_per_fold": wf_per_fold,
        "full_period": {
            "n_trades": full_m.n_trades,
            "win_rate": round(full_m.win_rate, 3),
            "expectancy_r": round(full_m.expectancy_r, 3),
            "expectancy_usd": round(full_m.expectancy_usd, 2),
            "total_pnl_usd": round(full_m.total_pnl_usd, 2),
            "max_dd_usd": round(full_m.max_drawdown_usd, 2),
            "max_dd_pct": round(full_m.max_drawdown_pct, 4),
            "sharpe": round(full_m.sharpe, 2),
        },
        "bootstrap": {
            "iterations": boot.n_iterations,
            "final_equity_mean": round(boot.final_equity_mean, 2),
            "final_equity_p05": round(boot.final_equity_p05, 2),
            "final_equity_p95": round(boot.final_equity_p95, 2),
            "max_dd_mean_pct": round(boot.max_dd_mean_pct, 4),
            "max_dd_p95_pct": round(boot.max_dd_p95_pct, 4),
            "prob_profitable": round(boot.prob_profitable, 3),
        },
        "session_breakdown": session_stats,
    }
    (out_dir / "report.json").write_text(
        json.dumps(report, indent=2, default=str),
    )

    # Also persist the per-trade tagged table for spreadsheet analysis
    trades_df = full.portfolio.trades_df()
    if not trades_df.is_empty():
        tags = [session_tag_at(t.entry_ts_ny, sess_cfg)
                for t in full.portfolio.trades]
        trades_df = trades_df.with_columns(pl.Series("session", tags))
        trades_df.write_csv(out_dir / "trades_tagged.csv")

    # Printout
    print("\n=== PILOT 004 — Winner re-WF + session breakdown ===\n")
    print(f"Cell: body_atr={WINNER['body_atr_min']}, body_range={WINNER['body_range_min']}, "
          f"fixed_tp_r={WINNER['fixed_tp_r']}, tp_strategy=fixed_R")
    print(f"Range: 2024-01-01 -> {bars.last_ts()}")
    print()
    print(f"WALK-FORWARD ({wf.n_folds} folds):")
    print(f"  folds positive : {sum(1 for f in wf.folds if f.metrics.expectancy_r > 0)}/{wf.n_folds}")
    print(f"  aggregate exp R: {wf.aggregate_expectancy_r():+.2f}")
    print(f"  aggregate PnL  : ${wf.aggregate_total_pnl():,.0f}")
    print()
    print("FULL PERIOD (with limits fix):")
    print(f"  trades         : {full_m.n_trades}")
    print(f"  win rate       : {full_m.win_rate:.1%}")
    print(f"  expectancy     : ${full_m.expectancy_usd:,.2f} / {full_m.expectancy_r:+.2f} R")
    print(f"  total PnL      : ${full_m.total_pnl_usd:,.2f}")
    print(f"  max drawdown   : ${full_m.max_drawdown_usd:,.2f} ({full_m.max_drawdown_pct:.2%})")
    print()
    print(f"BOOTSTRAP ({boot.n_iterations} iter):")
    print(f"  prob profitable: {boot.prob_profitable:.1%}")
    print(f"  max DD mean    : {boot.max_dd_mean_pct:.2%}  (p95 {boot.max_dd_p95_pct:.2%})")
    print()
    print("=== PER-KILLZONE BREAKDOWN ===")
    print(f"{'session':<22} {'trades':>7} {'WR':>6} {'exp R':>7} {'exp $':>10} {'total $':>12} {'%trades':>8} {'%PnL':>7}")
    print("-" * 90)
    for tag, s in sorted(session_stats.items(),
                          key=lambda kv: kv[1]["total_pnl_usd"],
                          reverse=True):
        print(
            f"{tag:<22} {s['n_trades']:>7} {s['win_rate']:>6.0%} "
            f"{s['expectancy_r']:>+7.2f} ${s['expectancy_usd']:>9,.0f} "
            f"${s['total_pnl_usd']:>11,.0f} {s['share_of_trades_pct']:>7.1f}% "
            f"{s['share_of_pnl_pct']:>6.1f}%",
        )
    print(f"\nArtifacts: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
