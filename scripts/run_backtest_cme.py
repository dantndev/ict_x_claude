"""End-to-end backtest pipeline using the cleaned CME continuous series.

Loads the multi-year MNQ (or NQ) continuous front-month from the Databento CSV,
optionally resamples, runs the full ICT pipeline, persists trades.csv +
equity.csv + summary.json + report.html under reports/runs/<run_id>/.

Usage:
    python scripts/run_backtest_cme.py
    python scripts/run_backtest_cme.py --family MNQ --tf 5m --from 2024-01-01
    python scripts/run_backtest_cme.py --family NQ  --tf 15m
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
from ict_bot.config.settings import REPO_ROOT, get_config
from ict_bot.data.loaders.cme_csv import load_cme_csv
from ict_bot.data.resampler import resample
from ict_bot.reporting.html_report import build_html_report
from ict_bot.reporting.metrics import compute_metrics, format_metrics
from ict_bot.risk.sizing import InstrumentSpec
from ict_bot.signals.imbalance.fvg import FVGConfig
from ict_bot.signals.setups.unicorn import UnicornConfig
from ict_bot.structure.displacement import DisplacementConfig
from ict_bot.utils.logging import configure_logging, get_logger

if isinstance(sys.stdout, io.TextIOWrapper):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def _instrument_for(family: str) -> InstrumentSpec:
    if family == "MNQ":
        cfg = get_config("mnq.yaml")
    else:
        cfg = get_config("nq.yaml")
    instr = cfg.get("instrument", {})
    return InstrumentSpec(
        tick_size=float(instr.get("tick_size", 0.25)),
        tick_value_usd=float(instr.get("tick_value_usd", 0.50)),
        point_value_usd=float(instr.get("point_value_usd", 2.0)),
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="CME-CSV-sourced backtest")
    p.add_argument("--csv",
                   default=str(REPO_ROOT / "data" / "cme_nq_2021_2026" / "datos_cme.csv"))
    p.add_argument("--family", default="MNQ", choices=["MNQ", "NQ"])
    p.add_argument("--tf", default="5m",
                   choices=["1m", "3m", "5m", "15m", "1H", "4H", "1D"])
    p.add_argument("--from", dest="start", type=_parse_date, default=None)
    p.add_argument("--to", dest="end", type=_parse_date, default=None)
    p.add_argument("--setup", default="all")
    p.add_argument("--starting-equity", type=float, default=100_000.0)
    p.add_argument("--no-killzones", action="store_true")
    p.add_argument("--no-midnight-filter", action="store_true")
    p.add_argument("--body-atr-min", type=float, default=1.5)
    p.add_argument("--body-range-min", type=float, default=0.6)
    p.add_argument("--min-rr", type=float, default=1.5)
    p.add_argument("--output-dir", default=str(REPO_ROOT / "reports" / "runs"))
    p.add_argument("--refresh-cache", action="store_true")
    args = p.parse_args(argv)

    configure_logging()
    log = get_logger("scripts.run_backtest_cme")

    bars_1m = load_cme_csv(
        args.csv, family=args.family,
        start=args.start, end=args.end,
        refresh=args.refresh_cache,
    )
    log.info("cme_loaded", bars=len(bars_1m), tf=bars_1m.tf,
             first=str(bars_1m.first_ts()), last=str(bars_1m.last_ts()))
    if bars_1m.empty:
        log.error("no_bars_in_range")
        return 2

    bars = resample(bars_1m, args.tf) if args.tf != "1m" else bars_1m
    log.info("bars_resampled", tf=bars.tf, bars=len(bars))

    setups: tuple[str, ...]
    if args.setup == "all":
        setups = ("unicorn", "mss_fvg", "ob_ote", "silver_bullet")
    else:
        setups = tuple(s.strip() for s in args.setup.split(","))

    from ict_bot.signals.setups.mss_fvg import MssFvgConfig
    from ict_bot.signals.setups.ob_ote import ObOteConfig
    from ict_bot.signals.setups.silver_bullet import SilverBulletConfig

    pcfg = PipelineConfig(
        setups=setups,
        displacement=DisplacementConfig(
            atr_lookback=14,
            body_atr_min=args.body_atr_min,
            body_range_min=args.body_range_min,
        ),
        fvg=FVGConfig(require_displacement=True, min_gap_ticks=1, tick_size=0.25),
        unicorn=UnicornConfig(min_rr=args.min_rr),
        mss_fvg=MssFvgConfig(min_rr=args.min_rr),
        ob_ote=ObOteConfig(min_rr=args.min_rr),
        silver_bullet=SilverBulletConfig(min_rr=args.min_rr),
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
    out_dir = Path(args.output_dir) / f"cme_{args.family}_{run_id}"
    out_dir.mkdir(parents=True, exist_ok=True)

    trades_df = result.portfolio.trades_df()
    equity_df = result.portfolio.equity_df()
    if not trades_df.is_empty():
        trades_df.write_csv(out_dir / "trades.csv")
    if not equity_df.is_empty():
        equity_df.write_csv(out_dir / "equity.csv")

    (out_dir / "summary.json").write_text(
        json.dumps(
            {
                "source": f"CME CSV (family={args.family})",
                "tf": args.tf, "setups": list(setups),
                "from": str(args.start), "to": str(args.end),
                "first_bar": str(bars.first_ts()), "last_bar": str(bars.last_ts()),
                "n_bars": len(bars),
                "starting_equity": args.starting_equity,
                "thresholds": {
                    "body_atr_min": args.body_atr_min,
                    "body_range_min": args.body_range_min,
                    "min_rr": args.min_rr,
                },
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
            },
            indent=2, default=str,
        ),
    )
    html = build_html_report(
        result.portfolio, out_dir,
        run_id=run_id,
        first_ts=bars.first_ts(), last_ts=bars.last_ts(),
        n_bars=len(bars),
        skipped_signals=result.skipped_signals,
        reasons_skipped=result.reasons_skipped,
    )
    print(f"\nArtifacts written to: {out_dir}")
    print(f"HTML report: {html}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
