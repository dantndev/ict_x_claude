"""PILOT 005b — TF sweep on mode B (Silver Bullet only).

Same production cell `(body_atr=1.0, body_range=0.5, fixed_tp_r=1.5,
tp_strategy=fixed_R)` and same session filter (silver_bullet_am +
silver_bullet_pm), but tested on 1m, 3m, 5m, 15m bars to see whether a
lower timeframe raises frequency enough to be worth the extra noise.

For each TF reports:
- Full-period: trades, trades/day, WR, exp R, PnL, MaxDD
- Worst single trade, max consecutive losers
- WF 8 folds: aggregate exp R, folds positive
- Bootstrap 1000: p95 MaxDD, prob_profitable

Decision rule: pick the TF that maximises `trades_per_day × expectancy_r`
while keeping max_consec_losers <= 8 (so the killswitch at 10 has margin).
"""

from __future__ import annotations

import io
import json
import sys
from collections import defaultdict
from datetime import date, datetime

from ict_bot.backtest.engine import BacktestConfig, run_backtest
from ict_bot.backtest.runner import PipelineConfig, detect_all_signals
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
TIMEFRAMES = ("1m", "3m", "5m", "15m")
SESSION_MODE = ("silver_bullet_am", "silver_bullet_pm")  # mode B


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


def _worst_month(trades: list) -> tuple[str, float, int]:
    by_month: dict[str, list[float]] = defaultdict(list)
    for t in trades:
        by_month[t.entry_ts_ny.strftime("%Y-%m")].append(t.pnl_usd)
    if not by_month:
        return ("n/a", 0.0, 0)
    sums = [(k, sum(v), len(v)) for k, v in by_month.items()]
    return min(sums, key=lambda x: x[1])


def main() -> int:
    configure_logging()
    log = get_logger("pilot.005b")

    bars_1m = load_cme_csv(
        REPO_ROOT / "data" / "cme_nq_2021_2026" / "datos_cme.csv",
        family="MNQ", start=date(2024, 1, 1),
    )
    log.info("base_bars_loaded", bars=len(bars_1m))

    pcfg = _build_pcfg()
    sess = SessionsConfig(allowed_windows=SESSION_MODE)
    bcfg = BacktestConfig(enforce_killzones=True, enforce_midnight_filter=True)

    rows: list[dict] = []
    for tf in TIMEFRAMES:
        log.info("tf_start", tf=tf)
        bars = resample(bars_1m, tf) if tf != "1m" else bars_1m  # type: ignore[arg-type]
        log.info("tf_bars_ready", tf=tf, bars=len(bars))
        n_days = max(1, (bars.last_ts() - bars.first_ts()).days)  # type: ignore[operator]

        # Walk-forward 8 folds
        wf = walk_forward(
            bars, n_folds=8, train_ratio=0.7, embargo_bars=60,
            pipeline_config=pcfg, backtest_config=bcfg,
        )

        # Full period with session filter
        signals = detect_all_signals(bars, cfg=pcfg)
        result = run_backtest(bars, signals, config=bcfg, sessions=sess)
        full_m = compute_metrics(result.portfolio)
        boot = bootstrap_stats(result.portfolio, iterations=1000)

        worst_trade = (
            min(t.pnl_usd for t in result.portfolio.trades)
            if result.portfolio.trades else 0.0
        )
        max_losers = _max_consecutive_losses(result.portfolio.trades)
        wm_key, wm_pnl, wm_n = _worst_month(result.portfolio.trades)

        rows.append({
            "tf": tf,
            "n_bars": len(bars),
            "n_days": n_days,
            "full_trades": full_m.n_trades,
            "trades_per_day": round(full_m.n_trades / n_days, 3),
            "win_rate": round(full_m.win_rate, 3),
            "expectancy_r": round(full_m.expectancy_r, 3),
            "expectancy_usd": round(full_m.expectancy_usd, 2),
            "pnl_usd": round(full_m.total_pnl_usd, 2),
            "max_dd_usd": round(full_m.max_drawdown_usd, 2),
            "max_dd_pct": round(full_m.max_drawdown_pct, 4),
            "worst_single_trade": round(worst_trade, 2),
            "max_consec_losers": max_losers,
            "worst_month": wm_key,
            "worst_month_pnl": round(wm_pnl, 2),
            "worst_month_n": wm_n,
            "wf_folds_pos": sum(1 for f in wf.folds if f.metrics.expectancy_r > 0),
            "wf_n_folds": wf.n_folds,
            "wf_agg_exp_r": round(wf.aggregate_expectancy_r(), 3),
            "wf_agg_pnl": round(wf.aggregate_total_pnl(), 2),
            "boot_p95_dd_pct": round(boot.max_dd_p95_pct, 4),
            "boot_prob_profit": round(boot.prob_profitable, 3),
            # Composite score: trades_per_day * expectancy_r, gated by safety
            "score": round(
                full_m.n_trades / n_days * full_m.expectancy_r,
                4,
            ),
        })
        log.info("tf_done", tf=tf, trades=full_m.n_trades,
                 trades_per_day=rows[-1]["trades_per_day"],
                 exp_r=full_m.expectancy_r,
                 max_consec=max_losers, pnl=full_m.total_pnl_usd)

    run_id = datetime.now().strftime("%Y%m%dT%H%M%S")
    out_dir = REPO_ROOT / "reports" / "pilots" / f"pilot_005b_{run_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(json.dumps(rows, indent=2, default=str))

    print("\n=== PILOT 005b — TF sweep on mode B (Silver Bullet only) ===\n")
    print(f"Cell: body_atr={WINNER['body_atr_min']}, body_range={WINNER['body_range_min']}, "
          f"fixed_tp_r={WINNER['fixed_tp_r']}\n")
    print(f"{'TF':<6} {'trades':>7} {'tr/day':>7} {'WR':>5} "
          f"{'exp R':>7} {'PnL':>11} {'MaxDD':>8} {'p95 DD':>8} "
          f"{'consec L':>9} {'WF folds':>9} {'WF agg R':>9} {'score':>8}")
    print("-" * 110)
    for r in rows:
        folds = f"{r['wf_folds_pos']}/{r['wf_n_folds']}"
        print(
            f"{r['tf']:<6} {r['full_trades']:>7} {r['trades_per_day']:>7.2f} "
            f"{r['win_rate']:>5.0%} {r['expectancy_r']:>+7.2f} "
            f"${r['pnl_usd']:>9,.0f} {r['max_dd_pct']:>7.2%} "
            f"{r['boot_p95_dd_pct']:>7.2%} {r['max_consec_losers']:>9} "
            f"{folds:>9} {r['wf_agg_exp_r']:>+9.2f} "
            f"{r['score']:>+8.3f}",
        )
    print(f"\nArtifacts: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
