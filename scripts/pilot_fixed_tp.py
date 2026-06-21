"""PILOT 002 — Fixed-R TP strategy sweep.

Hypothesis: under tp_strategy="nearest_pool" the dense pool registry forces
TPs into [1R, 1.5R) most of the time, so min_rr >= 1.5 starves the bot.
Switching to tp_strategy="fixed_R" places TP at exactly N×risk regardless of
pool layout, which should let us raise min_rr to 1.5-2.5 without killing
frequency.

Sweeps:
    body_atr_min ∈ {1.0, 1.5}
    min_rr       ∈ {1.0, 1.5, 2.0}
    fixed_tp_r   ∈ {1.5, 2.0, 2.5, 3.0}
    body_range_min held at 0.5 (plateau center from pilot 001)

= 24 cells. Outputs to reports/pilots/fixed_tp_<run_id>/.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import polars as pl

from ict_bot.backtest.engine import BacktestConfig
from ict_bot.backtest.runner import PipelineConfig, run_pipeline
from ict_bot.config.settings import REPO_ROOT
from ict_bot.data.loaders.cme_csv import load_cme_csv
from ict_bot.data.resampler import resample
from ict_bot.reporting.metrics import Metrics, compute_metrics
from ict_bot.signals.imbalance.fvg import FVGConfig
from ict_bot.signals.setups.mss_fvg import MssFvgConfig
from ict_bot.signals.setups.ob_ote import ObOteConfig
from ict_bot.signals.setups.silver_bullet import SilverBulletConfig
from ict_bot.signals.setups.unicorn import UnicornConfig
from ict_bot.structure.displacement import DisplacementConfig
from ict_bot.utils.logging import configure_logging, get_logger

if isinstance(sys.stdout, io.TextIOWrapper):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]


@dataclass(frozen=True, slots=True)
class Cell:
    body_atr_min: float
    body_range_min: float
    min_rr: float
    fixed_tp_r: float
    metrics: Metrics


@dataclass(slots=True)
class FixedTPResult:
    points: list[Cell] = field(default_factory=list)


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def sweep_fixed_tp(
    bars,
    *,
    body_atr_grid: tuple[float, ...],
    body_range_grid: tuple[float, ...],
    min_rr_grid: tuple[float, ...],
    fixed_tp_grid: tuple[float, ...],
    backtest_config: BacktestConfig,
) -> FixedTPResult:
    out = FixedTPResult()
    for atr in body_atr_grid:
        for br in body_range_grid:
            for rr in min_rr_grid:
                for ftpr in fixed_tp_grid:
                    if ftpr < rr:
                        # fixed TP smaller than min_rr → guaranteed rejection
                        continue
                    pcfg = PipelineConfig(
                        displacement=DisplacementConfig(
                            atr_lookback=14, body_atr_min=atr, body_range_min=br,
                        ),
                        fvg=FVGConfig(require_displacement=True,
                                       min_gap_ticks=1, tick_size=0.25),
                        unicorn=UnicornConfig(
                            min_rr=rr, tp_strategy="fixed_R", fixed_tp_r=ftpr,
                        ),
                        mss_fvg=MssFvgConfig(
                            min_rr=rr, tp_strategy="fixed_R", fixed_tp_r=ftpr,
                        ),
                        ob_ote=ObOteConfig(
                            min_rr=rr, tp_strategy="fixed_R", fixed_tp_r=ftpr,
                        ),
                        silver_bullet=SilverBulletConfig(
                            min_rr=rr, tp_strategy="fixed_R", fixed_tp_r=ftpr,
                        ),
                    )
                    res = run_pipeline(bars, pipeline_config=pcfg,
                                        backtest_config=backtest_config)
                    metrics = compute_metrics(res.portfolio)
                    out.points.append(Cell(
                        body_atr_min=atr, body_range_min=br, min_rr=rr,
                        fixed_tp_r=ftpr, metrics=metrics,
                    ))
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="PILOT 002 — fixed-R TP sweep")
    p.add_argument("--csv",
                   default=str(REPO_ROOT / "data" / "cme_nq_2021_2026" / "datos_cme.csv"))
    p.add_argument("--family", default="MNQ", choices=["MNQ", "NQ"])
    p.add_argument("--tf", default="5m",
                   choices=["1m", "3m", "5m", "15m", "1H", "4H", "1D"])
    p.add_argument("--from", dest="start", type=_parse_date, default=None)
    p.add_argument("--to", dest="end", type=_parse_date, default=None)
    p.add_argument("--output-dir", default=str(REPO_ROOT / "reports" / "pilots"))
    p.add_argument("--no-killzones", action="store_true")
    p.add_argument("--no-midnight-filter", action="store_true")
    args = p.parse_args(argv)

    configure_logging()
    log = get_logger("pilot.fixed_tp")

    bars_1m = load_cme_csv(args.csv, family=args.family,
                            start=args.start, end=args.end)
    bars = resample(bars_1m, args.tf) if args.tf != "1m" else bars_1m
    n_days = max(1, (bars.last_ts() - bars.first_ts()).days)  # type: ignore[operator]
    log.info("bars_ready", tf=bars.tf, bars=len(bars), days=n_days)

    bcfg = BacktestConfig(
        enforce_killzones=not args.no_killzones,
        enforce_midnight_filter=not args.no_midnight_filter,
    )
    result = sweep_fixed_tp(
        bars,
        body_atr_grid=(1.0, 1.5),
        body_range_grid=(0.5,),
        min_rr_grid=(1.0, 1.5, 2.0),
        fixed_tp_grid=(1.5, 2.0, 2.5, 3.0),
        backtest_config=bcfg,
    )

    rows = [
        {
            "body_atr_min": c.body_atr_min,
            "body_range_min": c.body_range_min,
            "min_rr": c.min_rr,
            "fixed_tp_r": c.fixed_tp_r,
            "n_trades": float(c.metrics.n_trades),
            "trades_per_day": round(c.metrics.n_trades / n_days, 3),
            "expectancy_r": c.metrics.expectancy_r,
            "win_rate": c.metrics.win_rate,
            "total_pnl_usd": c.metrics.total_pnl_usd,
            "max_dd_pct": c.metrics.max_drawdown_pct,
        }
        for c in result.points
    ]
    df = pl.DataFrame(rows).sort("expectancy_r", descending=True)

    run_id = datetime.now().strftime("%Y%m%dT%H%M%S")
    out_dir = Path(args.output_dir) / f"fixed_tp_{args.family}_{run_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    df.write_csv(out_dir / "grid.csv")
    (out_dir / "summary.json").write_text(
        json.dumps(
            {
                "family": args.family, "tf": args.tf,
                "from": str(bars.first_ts()), "to": str(bars.last_ts()),
                "n_bars": len(bars), "n_days": n_days,
                "n_cells": len(rows),
                "best_cell": df.row(0, named=True) if not df.is_empty() else None,
            },
            indent=2, default=str,
        ),
    )

    print("\n=== TOP 10 by expectancy_R ===")
    print(df.head(10))
    print(f"\nArtifacts: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
