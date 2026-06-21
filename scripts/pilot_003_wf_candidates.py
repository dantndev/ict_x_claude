"""PILOT 003 — Walk-forward the three pilot-002 fixed-R candidates.

Runs walk_forward + bootstrap independently for:
    A: (body_atr=1.0, body_range=0.5, fixed_tp_r=1.5)   ← max frequency
    B: (body_atr=1.5, body_range=0.5, fixed_tp_r=2.0)   ← balanced
    C: (body_atr=1.5, body_range=0.5, fixed_tp_r=2.5)   ← max selectivity

Emits one comparative report under reports/pilots/wf_candidates_<run_id>/.
This is independent and re-runnable; no production state is touched.
"""

from __future__ import annotations

import io
import json
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from ict_bot.backtest.engine import BacktestConfig
from ict_bot.backtest.runner import PipelineConfig, run_pipeline
from ict_bot.config.settings import REPO_ROOT
from ict_bot.data.loaders.cme_csv import load_cme_csv
from ict_bot.data.resampler import resample
from ict_bot.reporting.metrics import compute_metrics
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


@dataclass(frozen=True, slots=True)
class Candidate:
    name: str
    body_atr_min: float
    body_range_min: float
    fixed_tp_r: float


CANDIDATES: tuple[Candidate, ...] = (
    Candidate("A_max_freq",  1.0, 0.5, 1.5),
    Candidate("B_balanced",  1.5, 0.5, 2.0),
    Candidate("C_selective", 1.5, 0.5, 2.5),
)


def _build_pcfg(c: Candidate) -> PipelineConfig:
    return PipelineConfig(
        displacement=DisplacementConfig(
            atr_lookback=14,
            body_atr_min=c.body_atr_min,
            body_range_min=c.body_range_min,
        ),
        fvg=FVGConfig(require_displacement=True, min_gap_ticks=1, tick_size=0.25),
        unicorn=UnicornConfig(
            min_rr=1.0, tp_strategy="fixed_R", fixed_tp_r=c.fixed_tp_r,
        ),
        mss_fvg=MssFvgConfig(
            min_rr=1.0, tp_strategy="fixed_R", fixed_tp_r=c.fixed_tp_r,
        ),
        ob_ote=ObOteConfig(
            min_rr=1.0, tp_strategy="fixed_R", fixed_tp_r=c.fixed_tp_r,
        ),
        silver_bullet=SilverBulletConfig(
            min_rr=1.0, tp_strategy="fixed_R", fixed_tp_r=c.fixed_tp_r,
        ),
    )


def main() -> int:
    configure_logging()
    log = get_logger("pilot.003")

    bars_1m = load_cme_csv(
        REPO_ROOT / "data" / "cme_nq_2021_2026" / "datos_cme.csv",
        family="MNQ", start=date(2024, 1, 1),
    )
    bars = resample(bars_1m, "5m")
    log.info("bars_ready", tf=bars.tf, bars=len(bars))

    bcfg = BacktestConfig(enforce_killzones=True, enforce_midnight_filter=True)
    results: list[dict[str, object]] = []

    for c in CANDIDATES:
        log.info("candidate_start", name=c.name,
                 atr=c.body_atr_min, br=c.body_range_min, tp_r=c.fixed_tp_r)
        pcfg = _build_pcfg(c)
        # 8-fold WF with 70/30 split and 60-bar embargo
        wf = walk_forward(
            bars, n_folds=8, train_ratio=0.7, embargo_bars=60,
            pipeline_config=pcfg, backtest_config=bcfg,
        )
        # Full-period for bootstrap
        full = run_pipeline(bars, pipeline_config=pcfg, backtest_config=bcfg)
        full_m = compute_metrics(full.portfolio)
        boot = bootstrap_stats(full.portfolio, iterations=1000)

        per_fold = [
            {
                "fold": f.fold_index,
                "n_trades": f.metrics.n_trades,
                "exp_r": round(f.metrics.expectancy_r, 3),
                "pnl_usd": round(f.metrics.total_pnl_usd, 2),
                "win_rate": round(f.metrics.win_rate, 3),
            }
            for f in wf.folds
        ]
        results.append({
            "name": c.name,
            "body_atr_min": c.body_atr_min,
            "body_range_min": c.body_range_min,
            "fixed_tp_r": c.fixed_tp_r,
            "wf_folds_positive": sum(1 for f in wf.folds if f.metrics.expectancy_r > 0),
            "wf_n_folds": wf.n_folds,
            "wf_aggregate_exp_r": round(wf.aggregate_expectancy_r(), 3),
            "wf_aggregate_pnl_usd": round(wf.aggregate_total_pnl(), 2),
            "wf_per_fold": per_fold,
            "full_n_trades": full_m.n_trades,
            "full_exp_r": round(full_m.expectancy_r, 3),
            "full_pnl_usd": round(full_m.total_pnl_usd, 2),
            "full_win_rate": round(full_m.win_rate, 3),
            "full_max_dd_pct": round(full_m.max_drawdown_pct, 4),
            "bootstrap_max_dd_mean_pct": round(boot.max_dd_mean_pct, 4),
            "bootstrap_max_dd_p95_pct": round(boot.max_dd_p95_pct, 4),
            "bootstrap_prob_profitable": round(boot.prob_profitable, 3),
        })
        log.info("candidate_done", name=c.name,
                 wf_exp_r=wf.aggregate_expectancy_r(),
                 wf_pnl=wf.aggregate_total_pnl())

    run_id = datetime.now().strftime("%Y%m%dT%H%M%S")
    out_dir = Path(REPO_ROOT) / "reports" / "pilots" / f"wf_candidates_{run_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(
        json.dumps(results, indent=2, default=str),
    )

    # Compact summary printout
    print("\n=== PILOT 003 — Walk-forward comparison ===\n")
    header = f"{'name':<14} {'WF folds+':<10} {'WF agg R':<10} {'WF agg $':<14} {'Full N':<8} {'Full R':<8} {'WR':<6}"
    print(header)
    print("-" * len(header))
    for r in results:
        print(
            f"{r['name']:<14} "
            f"{str(r['wf_folds_positive']) + '/' + str(r['wf_n_folds']):<10} "
            f"{r['wf_aggregate_exp_r']:<+10.2f} "
            f"${r['wf_aggregate_pnl_usd']:<13,.0f} "
            f"{r['full_n_trades']:<8} "
            f"{r['full_exp_r']:<+8.2f} "
            f"{r['full_win_rate']:<6.0%}",
        )
    print(f"\nArtifacts: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
