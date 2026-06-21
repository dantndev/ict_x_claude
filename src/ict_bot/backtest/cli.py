"""CLI: ict-backtest — fetch bars, run pipeline, print metrics, write reports."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from ict_bot.backtest.engine import BacktestConfig
from ict_bot.backtest.runner import PipelineConfig, run_pipeline
from ict_bot.config.settings import REPO_ROOT
from ict_bot.data.loaders.ohlcv_http import fetch_ohlcv_1m
from ict_bot.data.resampler import resample
from ict_bot.reporting.metrics import compute_metrics, format_metrics
from ict_bot.utils.logging import configure_logging, get_logger


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="ICT backtest runner")
    p.add_argument("--tf", default="5m",
                   choices=["1m", "3m", "5m", "15m", "1H", "4H", "1D"],
                   help="Timeframe for setup detection (bars are resampled from 1m)")
    p.add_argument("--from", dest="start", default=None, help="Start ISO datetime (NY)")
    p.add_argument("--to", dest="end", default=None, help="End ISO datetime (NY)")
    p.add_argument("--setup", default="all",
                   help="Comma-separated subset: unicorn,mss_fvg,ob_ote,silver_bullet")
    p.add_argument("--starting-equity", type=float, default=100_000.0)
    p.add_argument("--no-killzones", action="store_true",
                   help="Disable killzone gating (for ablation)")
    p.add_argument("--no-midnight-filter", action="store_true")
    p.add_argument("--refresh-data", action="store_true")
    p.add_argument("--output-dir", default=str(REPO_ROOT / "reports" / "runs"),
                   help="Where to write trades.csv, equity.csv, summary.json")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    configure_logging()
    log = get_logger("ict_bot.backtest.cli")

    log.info("fetch_start")
    bars_1m = fetch_ohlcv_1m(use_cache=not args.refresh_data, refresh=args.refresh_data)
    log.info("fetch_done", bars=len(bars_1m), tf=bars_1m.tf)

    if args.start is not None or args.end is not None:
        start = datetime.fromisoformat(args.start) if args.start else None
        end = datetime.fromisoformat(args.end) if args.end else None
        bars_1m = bars_1m.slice(start=start, end=end)
        log.info("range_sliced", bars=len(bars_1m))

    bars = resample(bars_1m, args.tf) if args.tf != "1m" else bars_1m
    log.info("resampled", tf=bars.tf, bars=len(bars))

    setups: tuple[str, ...]
    if args.setup == "all":
        setups = ("unicorn", "mss_fvg", "ob_ote", "silver_bullet")
    else:
        setups = tuple(s.strip() for s in args.setup.split(","))
    pcfg = PipelineConfig(setups=setups)
    bcfg = BacktestConfig(
        starting_equity=args.starting_equity,
        enforce_killzones=not args.no_killzones,
        enforce_midnight_filter=not args.no_midnight_filter,
    )

    result = run_pipeline(bars, pipeline_config=pcfg, backtest_config=bcfg)
    metrics = compute_metrics(result.portfolio)
    print(format_metrics(metrics))
    print(f"\nSkipped signals: {result.skipped_signals}  Reasons: {result.reasons_skipped}")

    # Persist artifacts
    run_id = datetime.now().strftime("%Y%m%dT%H%M%S")
    out_dir = Path(args.output_dir) / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    result.portfolio.trades_df().write_csv(out_dir / "trades.csv")
    result.portfolio.equity_df().write_csv(out_dir / "equity.csv")
    (out_dir / "summary.json").write_text(
        json.dumps(
            {
                "tf": args.tf,
                "setups": setups,
                "starting_equity": args.starting_equity,
                "metrics": {
                    "n_trades": metrics.n_trades,
                    "win_rate": metrics.win_rate,
                    "profit_factor": (metrics.profit_factor
                                      if metrics.profit_factor != float("inf")
                                      else None),
                    "expectancy_r": metrics.expectancy_r,
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
            },
            indent=2, default=str,
        ),
    )
    print(f"\nArtifacts written to: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
