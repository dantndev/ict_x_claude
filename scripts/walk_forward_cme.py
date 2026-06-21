"""Walk-forward + Monte Carlo bootstrap on CME continuous bars.

Usage:
    python scripts/walk_forward_cme.py --family MNQ --tf 5m --folds 5
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from datetime import date, datetime
from pathlib import Path

from ict_bot.backtest.engine import BacktestConfig
from ict_bot.backtest.runner import PipelineConfig, run_pipeline
from ict_bot.config.settings import REPO_ROOT
from ict_bot.data.loaders.cme_csv import load_cme_csv
from ict_bot.data.resampler import resample
from ict_bot.reporting.metrics import compute_metrics
from ict_bot.signals.imbalance.fvg import FVGConfig
from ict_bot.signals.setups.unicorn import UnicornConfig
from ict_bot.structure.displacement import DisplacementConfig
from ict_bot.utils.logging import configure_logging, get_logger
from ict_bot.validation.bootstrap import bootstrap_stats
from ict_bot.validation.walk_forward import walk_forward

if isinstance(sys.stdout, io.TextIOWrapper):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Walk-forward + Monte Carlo")
    p.add_argument("--csv",
                   default=str(REPO_ROOT / "data" / "cme_nq_2021_2026" / "datos_cme.csv"))
    p.add_argument("--family", default="MNQ", choices=["MNQ", "NQ"])
    p.add_argument("--tf", default="5m",
                   choices=["1m", "3m", "5m", "15m", "1H", "4H", "1D"])
    p.add_argument("--from", dest="start", type=_parse_date, default=None)
    p.add_argument("--to", dest="end", type=_parse_date, default=None)
    p.add_argument("--folds", type=int, default=5)
    p.add_argument("--train-ratio", type=float, default=0.6)
    p.add_argument("--embargo-bars", type=int, default=60)
    p.add_argument("--bootstrap-iter", type=int, default=1000)
    p.add_argument("--body-atr-min", type=float, default=1.5)
    p.add_argument("--body-range-min", type=float, default=0.6)
    p.add_argument("--min-rr", type=float, default=1.5)
    p.add_argument("--no-killzones", action="store_true")
    p.add_argument("--no-midnight-filter", action="store_true")
    p.add_argument("--tp-strategy", default="nearest_pool",
                   choices=["nearest_pool", "fixed_R"])
    p.add_argument("--fixed-tp-r", type=float, default=2.0)
    p.add_argument("--output-dir", default=str(REPO_ROOT / "reports" / "validation"))
    args = p.parse_args(argv)

    configure_logging()
    log = get_logger("scripts.walk_forward_cme")

    bars_1m = load_cme_csv(
        args.csv, family=args.family, start=args.start, end=args.end,
    )
    bars = resample(bars_1m, args.tf) if args.tf != "1m" else bars_1m
    log.info("bars_ready", tf=bars.tf, bars=len(bars))

    from ict_bot.signals.setups.mss_fvg import MssFvgConfig
    from ict_bot.signals.setups.ob_ote import ObOteConfig
    from ict_bot.signals.setups.silver_bullet import SilverBulletConfig

    pcfg = PipelineConfig(
        displacement=DisplacementConfig(
            atr_lookback=14, body_atr_min=args.body_atr_min,
            body_range_min=args.body_range_min,
        ),
        fvg=FVGConfig(require_displacement=True, min_gap_ticks=1, tick_size=0.25),
        unicorn=UnicornConfig(
            min_rr=args.min_rr,
            tp_strategy=args.tp_strategy, fixed_tp_r=args.fixed_tp_r,
        ),
        mss_fvg=MssFvgConfig(
            min_rr=args.min_rr,
            tp_strategy=args.tp_strategy, fixed_tp_r=args.fixed_tp_r,
        ),
        ob_ote=ObOteConfig(
            min_rr=args.min_rr,
            tp_strategy=args.tp_strategy, fixed_tp_r=args.fixed_tp_r,
        ),
        silver_bullet=SilverBulletConfig(
            min_rr=args.min_rr,
            tp_strategy=args.tp_strategy, fixed_tp_r=args.fixed_tp_r,
        ),
    )
    bcfg = BacktestConfig(
        enforce_killzones=not args.no_killzones,
        enforce_midnight_filter=not args.no_midnight_filter,
    )

    wf = walk_forward(
        bars, n_folds=args.folds, train_ratio=args.train_ratio,
        embargo_bars=args.embargo_bars,
        pipeline_config=pcfg, backtest_config=bcfg,
    )
    print(f"\nWalk-forward: {wf.n_folds} folds")
    for f in wf.folds:
        print(f"  Fold {f.fold_index}: test {f.test_start.date()} -> {f.test_end.date()}  "
              f"trades={f.metrics.n_trades}  exp_r={f.metrics.expectancy_r:+.2f}  "
              f"pnl=${f.metrics.total_pnl_usd:,.0f}")
    print(f"Aggregate expectancy R: {wf.aggregate_expectancy_r():+.2f}")
    print(f"Aggregate test PnL:     ${wf.aggregate_total_pnl():,.2f}")

    # Bootstrap over the full-period pipeline result for stability stats
    full = run_pipeline(bars, pipeline_config=pcfg, backtest_config=bcfg)
    full_metrics = compute_metrics(full.portfolio)
    stats = bootstrap_stats(full.portfolio, iterations=args.bootstrap_iter)
    print(f"\nFull-period trades: {full_metrics.n_trades}  "
          f"exp_r={full_metrics.expectancy_r:+.2f}")
    print(f"Bootstrap ({stats.n_iterations} iter):")
    print(f"  final equity mean: ${stats.final_equity_mean:,.2f}  "
          f"[p05 ${stats.final_equity_p05:,.0f} - p95 ${stats.final_equity_p95:,.0f}]")
    print(f"  max DD mean:       {stats.max_dd_mean_pct:.1%}  "
          f"(p95 {stats.max_dd_p95_pct:.1%})")
    print(f"  prob profitable:   {stats.prob_profitable:.1%}")

    run_id = datetime.now().strftime("%Y%m%dT%H%M%S")
    out_dir = Path(args.output_dir) / f"wf_{args.family}_{run_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "walk_forward.json").write_text(
        json.dumps(
            {
                "family": args.family, "tf": args.tf,
                "folds": [
                    {
                        "fold_index": f.fold_index,
                        "test_start": str(f.test_start),
                        "test_end": str(f.test_end),
                        "n_trades": f.metrics.n_trades,
                        "expectancy_r": f.metrics.expectancy_r,
                        "total_pnl_usd": f.metrics.total_pnl_usd,
                        "max_dd_pct": f.metrics.max_drawdown_pct,
                    }
                    for f in wf.folds
                ],
                "aggregate_expectancy_r": wf.aggregate_expectancy_r(),
                "aggregate_total_pnl_usd": wf.aggregate_total_pnl(),
                "bootstrap": {
                    "n_iterations": stats.n_iterations,
                    "final_equity_mean": stats.final_equity_mean,
                    "final_equity_p05": stats.final_equity_p05,
                    "final_equity_p95": stats.final_equity_p95,
                    "max_dd_mean_pct": stats.max_dd_mean_pct,
                    "max_dd_p95_pct": stats.max_dd_p95_pct,
                    "prob_profitable": stats.prob_profitable,
                },
            },
            indent=2, default=str,
        ),
    )
    print(f"\nArtifacts: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
