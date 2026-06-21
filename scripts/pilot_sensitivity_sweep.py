"""PILOT — Threshold sensitivity sweep over the 5-year CME continuous.

Independent experiment: NOT part of the production pipeline. Designed to
answer "what threshold combinations trade more often while keeping edge?"
on real historical data, without inventing new strategy concepts.

Sweeps the grid:
    body_atr_min    × body_range_min × min_rr
    {0.8, 1.0, 1.5} × {0.4, 0.5, 0.6} × {1.0, 1.5, 2.0}    (default = 27 cells)

For each cell:
    1. Runs the full pipeline on the requested date range and timeframe.
    2. Computes n_trades, trades_per_day, expectancy_R, total_pnl, max_dd.
    3. Persists a CSV + Markdown summary in reports/pilots/sensitivity_<ts>/.

Use:
    python scripts/pilot_sensitivity_sweep.py
    python scripts/pilot_sensitivity_sweep.py --family MNQ --tf 1m --from 2024-01-01
    python scripts/pilot_sensitivity_sweep.py --grid extended      # 4×4×4 = 64 cells
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from datetime import date, datetime
from pathlib import Path

import polars as pl

from ict_bot.backtest.engine import BacktestConfig
from ict_bot.config.settings import REPO_ROOT
from ict_bot.data.loaders.cme_csv import load_cme_csv
from ict_bot.data.resampler import resample
from ict_bot.utils.logging import configure_logging, get_logger
from ict_bot.validation.sensitivity import sweep_displacement

if isinstance(sys.stdout, io.TextIOWrapper):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]


_GRIDS: dict[str, dict[str, tuple[float, ...]]] = {
    "default": {
        "body_atr": (0.8, 1.0, 1.5),
        "body_range": (0.4, 0.5, 0.6),
        "min_rr": (1.0, 1.5, 2.0),
    },
    "extended": {
        "body_atr": (0.6, 0.8, 1.0, 1.5),
        "body_range": (0.3, 0.4, 0.5, 0.6),
        "min_rr": (0.8, 1.0, 1.5, 2.0),
    },
    "fine": {
        "body_atr": (0.8, 0.9, 1.0, 1.1, 1.25, 1.5),
        "body_range": (0.4, 0.5, 0.6),
        "min_rr": (1.0, 1.25, 1.5, 2.0),
    },
}


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="PILOT — sensitivity sweep on CME")
    p.add_argument("--csv",
                   default=str(REPO_ROOT / "data" / "cme_nq_2021_2026" / "datos_cme.csv"))
    p.add_argument("--family", default="MNQ", choices=["MNQ", "NQ"])
    p.add_argument("--tf", default="5m",
                   choices=["1m", "3m", "5m", "15m", "1H", "4H", "1D"])
    p.add_argument("--from", dest="start", type=_parse_date, default=None)
    p.add_argument("--to", dest="end", type=_parse_date, default=None)
    p.add_argument("--grid", default="default",
                   choices=list(_GRIDS.keys()),
                   help="default=27 cells, extended=64, fine=72")
    p.add_argument("--output-dir", default=str(REPO_ROOT / "reports" / "pilots"))
    p.add_argument("--no-killzones", action="store_true")
    p.add_argument("--no-midnight-filter", action="store_true")
    args = p.parse_args(argv)

    configure_logging()
    log = get_logger("pilot.sensitivity")

    bars_1m = load_cme_csv(args.csv, family=args.family,
                            start=args.start, end=args.end)
    bars = resample(bars_1m, args.tf) if args.tf != "1m" else bars_1m
    log.info("bars_ready", tf=bars.tf, bars=len(bars),
             first=str(bars.first_ts()), last=str(bars.last_ts()))
    if bars.empty:
        log.error("no_bars_in_range")
        return 2

    # Approx trading days for trades/day metric
    n_days = max(1, (bars.last_ts() - bars.first_ts()).days)  # type: ignore[operator]

    grid = _GRIDS[args.grid]
    n_cells = (len(grid["body_atr"]) * len(grid["body_range"])
               * len(grid["min_rr"]))
    log.info("sweep_start", cells=n_cells, grid=args.grid)

    bcfg = BacktestConfig(
        enforce_killzones=not args.no_killzones,
        enforce_midnight_filter=not args.no_midnight_filter,
    )
    result = sweep_displacement(
        bars,
        body_atr_grid=grid["body_atr"],
        body_range_grid=grid["body_range"],
        min_rr_grid=grid["min_rr"],
        backtest_config=bcfg,
    )

    rows = result.to_table()
    for r in rows:
        r["trades_per_day"] = round(r["n_trades"] / n_days, 3)

    df = pl.DataFrame(rows).sort("expectancy_r", descending=True)
    run_id = datetime.now().strftime("%Y%m%dT%H%M%S")
    out_dir = Path(args.output_dir) / f"sensitivity_{args.family}_{run_id}"
    out_dir.mkdir(parents=True, exist_ok=True)

    df.write_csv(out_dir / "grid.csv")

    best = df.head(10)
    worst = df.tail(5)

    def _md_table(frame: pl.DataFrame) -> str:
        if frame.is_empty():
            return "_(empty)_"
        cols = frame.columns
        header = "| " + " | ".join(cols) + " |"
        sep = "| " + " | ".join("---" for _ in cols) + " |"
        rows_md = []
        for row in frame.iter_rows(named=True):
            rows_md.append(
                "| " + " | ".join(
                    f"{v:.3f}" if isinstance(v, float) else str(v) for v in row.values()
                ) + " |",
            )
        return "\n".join([header, sep, *rows_md])

    md_lines = [
        f"# Sensitivity sweep — {args.family} {args.tf}",
        "",
        f"- Range: `{bars.first_ts()}` → `{bars.last_ts()}` ({n_days} days, {len(bars)} bars)",
        f"- Grid: `{args.grid}` ({n_cells} cells)",
        f"- Killzones: {'on' if not args.no_killzones else 'OFF'}  "
        f"Midnight filter: {'on' if not args.no_midnight_filter else 'OFF'}",
        "",
        "## Top 10 by expectancy_R",
        "",
        _md_table(df.head(10)),
        "",
        "## Worst 5 by expectancy_R",
        "",
        _md_table(worst),
        "",
        "## Interpretation",
        "",
        "- A *robust plateau* is a cluster of adjacent cells with similar high "
        "expectancy — prefer the plateau center, NOT the absolute peak (which "
        "is often an overfit artifact).",
        "- `trades_per_day` quantifies the frequency cost of stricter thresholds.",
        "- Cells with `n_trades` < 30 are statistically weak — do not draw "
        "conclusions from them.",
    ]
    (out_dir / "report.md").write_text("\n".join(md_lines), encoding="utf-8")

    (out_dir / "summary.json").write_text(
        json.dumps(
            {
                "family": args.family, "tf": args.tf,
                "from": str(bars.first_ts()), "to": str(bars.last_ts()),
                "n_bars": len(bars), "n_days": n_days,
                "grid_name": args.grid, "n_cells": n_cells,
                "best_cell": best.row(0, named=True) if not best.is_empty() else None,
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
