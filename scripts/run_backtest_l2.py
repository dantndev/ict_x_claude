"""End-to-end backtest using the L2 CSVs as the source of bars.

Builds OHLCV from the L2 tick mid, resamples to 5m, runs the full Phase-3/4/5
pipeline, prints metrics, and writes artifacts under reports/runs/<run_id>/.

Usage:
    python scripts/run_backtest_l2.py
    python scripts/run_backtest_l2.py --tf 15m --from 2026-06-01 --to 2026-06-17
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from datetime import date, datetime
from pathlib import Path

# Force UTF-8 stdout for any unicode in metric formatting (Windows cp1252)
if isinstance(sys.stdout, io.TextIOWrapper):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

from ict_bot.backtest.engine import BacktestConfig
from ict_bot.backtest.runner import PipelineConfig, run_pipeline
from ict_bot.config.settings import REPO_ROOT, get_settings
from ict_bot.data.loaders.l2_csv import list_available_days, load_range
from ict_bot.data.resampler import bars_from_ticks, resample
from ict_bot.reporting.metrics import compute_metrics, format_metrics
from ict_bot.utils.logging import configure_logging, get_logger


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="L2-sourced backtest")
    p.add_argument("--tf", default="5m",
                   choices=["1m", "3m", "5m", "15m", "1H", "4H", "1D"])
    p.add_argument("--from", dest="start", type=_parse_date, default=None)
    p.add_argument("--to", dest="end", type=_parse_date, default=None)
    p.add_argument("--setup", default="all",
                   help="Comma-separated: unicorn,mss_fvg,ob_ote,silver_bullet")
    p.add_argument("--starting-equity", type=float, default=100_000.0)
    p.add_argument("--no-killzones", action="store_true")
    p.add_argument("--no-midnight-filter", action="store_true")
    p.add_argument("--body-atr-min", type=float, default=1.0,
                   help="Override displacement body/ATR threshold (1.5 is strict; "
                        "lower to expose more legs for L2-mid bars)")
    p.add_argument("--body-range-min", type=float, default=0.4)
    p.add_argument("--min-rr", type=float, default=1.0)
    p.add_argument("--output-dir", default=str(REPO_ROOT / "reports" / "runs"))
    args = p.parse_args(argv)

    configure_logging()
    log = get_logger("scripts.run_backtest_l2")
    settings = get_settings()

    days = list_available_days()
    if not days:
        log.error("no_l2_days_found", dir=str(settings.ict_l2_csv_dir))
        return 1
    start = args.start or days[0]
    end = args.end or days[-1]
    log.info("l2_range", start=str(start), end=str(end),
             total_available=len(days))

    ticks = load_range(start, end)
    log.info("l2_loaded", ticks=len(ticks))
    if len(ticks) == 0:
        log.error("no_ticks_in_range")
        return 2

    bars_1m = bars_from_ticks(ticks.df, symbol=settings.ict_symbol, target_tf="1m")
    log.info("bars_built_1m", bars=len(bars_1m))

    bars = resample(bars_1m, args.tf) if args.tf != "1m" else bars_1m
    log.info("bars_resampled", tf=bars.tf, bars=len(bars))

    setups: tuple[str, ...]
    if args.setup == "all":
        setups = ("unicorn", "mss_fvg", "ob_ote", "silver_bullet")
    else:
        setups = tuple(s.strip() for s in args.setup.split(","))

    from ict_bot.signals.imbalance.fvg import FVGConfig
    from ict_bot.signals.setups.unicorn import UnicornConfig
    from ict_bot.structure.displacement import DisplacementConfig

    pcfg = PipelineConfig(
        setups=setups,
        displacement=DisplacementConfig(
            atr_lookback=14,
            body_atr_min=args.body_atr_min,
            body_range_min=args.body_range_min,
        ),
        fvg=FVGConfig(require_displacement=True, min_gap_ticks=1, tick_size=0.25),
        unicorn=UnicornConfig(min_rr=args.min_rr),
    )
    bcfg = BacktestConfig(
        starting_equity=args.starting_equity,
        enforce_killzones=not args.no_killzones,
        enforce_midnight_filter=not args.no_midnight_filter,
    )

    result = run_pipeline(bars, pipeline_config=pcfg, backtest_config=bcfg)
    metrics = compute_metrics(result.portfolio)
    print(format_metrics(metrics))
    print(f"\nSkipped signals: {result.skipped_signals}  Reasons: {result.reasons_skipped}")

    run_id = datetime.now().strftime("%Y%m%dT%H%M%S")
    out_dir = Path(args.output_dir) / f"l2_{run_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    trades_df = result.portfolio.trades_df()
    equity_df = result.portfolio.equity_df()
    if trades_df.is_empty():
        (out_dir / "trades.csv").write_text("")
    else:
        trades_df.write_csv(out_dir / "trades.csv")
    if equity_df.is_empty():
        (out_dir / "equity.csv").write_text("")
    else:
        equity_df.write_csv(out_dir / "equity.csv")
    (out_dir / "summary.json").write_text(
        json.dumps(
            {
                "source": "L2 CSVs",
                "range": {"from": str(start), "to": str(end)},
                "tf": args.tf,
                "setups": list(setups),
                "starting_equity": args.starting_equity,
                "metrics": {
                    "n_trades": metrics.n_trades,
                    "n_wins": metrics.n_wins,
                    "n_losses": metrics.n_losses,
                    "win_rate": metrics.win_rate,
                    "profit_factor": (metrics.profit_factor
                                      if metrics.profit_factor != float("inf")
                                      else None),
                    "expectancy_r": metrics.expectancy_r,
                    "expectancy_usd": metrics.expectancy_usd,
                    "total_pnl_usd": metrics.total_pnl_usd,
                    "final_equity": metrics.final_equity,
                    "max_drawdown_usd": metrics.max_drawdown_usd,
                    "max_drawdown_pct": metrics.max_drawdown_pct,
                    "sharpe": metrics.sharpe,
                    "sortino": metrics.sortino,
                },
                "skipped_signals": result.skipped_signals,
                "reasons_skipped": result.reasons_skipped,
                "first_bar": str(bars.first_ts()),
                "last_bar": str(bars.last_ts()),
                "n_bars": len(bars),
            },
            indent=2, default=str,
        ),
    )
    print(f"\nArtifacts written to: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
