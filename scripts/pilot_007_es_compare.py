"""PILOT 007 — Validate the production cell on ES (MES economy).

Same idea as before, but **without the 8-fold walk-forward** because ES on
1m generates ~3.9x more swings than NQ on 1m (microstructure granularity
of a higher-priced index), and the FVG/OB detectors are O(swings × bars)
in the worst case — running WF over the full 2024-2026 range took >1 h
and never finished.

Strategy now:
  1. Smoke-test on a single recent month to confirm cell still produces
     trades on ES.
  2. Full-period run (one pass) on 2025-01-01 → end, single pipeline call,
     plus bootstrap 1000.
  3. Calendar-day overlap with the NQ baseline so the correlation risk
     for dual-instrument operation is visible without a heavy compute.

If the full-period ES numbers look promising AND overlap < 60%, a
follow-up pilot (007b) does the proper walk-forward in chunks.
"""

from __future__ import annotations

import io
import json
import sys
import time
from datetime import date, datetime

from ict_bot.backtest.engine import BacktestConfig, run_backtest
from ict_bot.backtest.runner import PipelineConfig, detect_all_signals
from ict_bot.config.settings import REPO_ROOT
from ict_bot.data.loaders.cme_csv import load_cme_csv
from ict_bot.reporting.metrics import compute_metrics
from ict_bot.risk.sizing import InstrumentSpec
from ict_bot.sessions.killzones import SessionsConfig
from ict_bot.signals.imbalance.fvg import FVGConfig
from ict_bot.signals.setups.mss_fvg import MssFvgConfig
from ict_bot.signals.setups.ob_ote import ObOteConfig
from ict_bot.signals.setups.silver_bullet import SilverBulletConfig
from ict_bot.signals.setups.unicorn import UnicornConfig
from ict_bot.structure.displacement import DisplacementConfig
from ict_bot.utils.logging import configure_logging, get_logger
from ict_bot.validation.bootstrap import bootstrap_stats

if isinstance(sys.stdout, io.TextIOWrapper):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]


WINNER = {"body_atr_min": 1.0, "body_range_min": 0.5, "fixed_tp_r": 1.5}
MES_SPEC = InstrumentSpec(tick_size=0.25, tick_value_usd=1.25, point_value_usd=5.0)
MNQ_SPEC = InstrumentSpec(tick_size=0.25, tick_value_usd=0.50, point_value_usd=2.0)


def _pcfg() -> PipelineConfig:
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


def _max_consec_losses(trades: list) -> int:
    streak = 0
    worst = 0
    for t in sorted(trades, key=lambda x: x.entry_ts_ny):
        if t.pnl_usd < 0:
            streak += 1
            worst = max(worst, streak)
        else:
            streak = 0
    return worst


def _run_full_period(name: str, bars, instrument: InstrumentSpec, log) -> dict:
    t0 = time.time()
    sess = SessionsConfig(allowed_windows=("silver_bullet_am", "silver_bullet_pm"))
    bcfg = BacktestConfig(enforce_killzones=True, enforce_midnight_filter=True)
    pcfg = _pcfg()
    n_days = max(1, (bars.last_ts() - bars.first_ts()).days)  # type: ignore[operator]
    log.info(f"{name}_pipeline_start", bars=len(bars), n_days=n_days)

    signals = detect_all_signals(bars, cfg=pcfg)
    log.info(f"{name}_signals_ready", count=len(signals),
             elapsed_s=round(time.time() - t0, 1))

    result = run_backtest(bars, signals, config=bcfg, sessions=sess,
                          instrument=instrument)
    m = compute_metrics(result.portfolio)
    boot = bootstrap_stats(result.portfolio, iterations=1000)
    log.info(f"{name}_done", trades=m.n_trades, exp_r=m.expectancy_r,
             pnl=m.total_pnl_usd, elapsed_s=round(time.time() - t0, 1))

    return {
        "name": name,
        "n_bars": len(bars),
        "n_days": n_days,
        "trades": m.n_trades,
        "trades_per_day": round(m.n_trades / n_days, 3),
        "win_rate": round(m.win_rate, 3),
        "expectancy_r": round(m.expectancy_r, 3),
        "expectancy_usd": round(m.expectancy_usd, 2),
        "pnl_usd": round(m.total_pnl_usd, 2),
        "max_dd_usd": round(m.max_drawdown_usd, 2),
        "max_dd_pct": round(m.max_drawdown_pct, 4),
        "worst_trade": round(
            min((t.pnl_usd for t in result.portfolio.trades), default=0.0), 2,
        ),
        "max_consec_losers": _max_consec_losses(result.portfolio.trades),
        "boot_p95_dd_pct": round(boot.max_dd_p95_pct, 4),
        "boot_prob_profit": round(boot.prob_profitable, 3),
        "_trade_days": {t.entry_ts_ny.strftime("%Y-%m-%d")
                         for t in result.portfolio.trades},
    }


def main() -> int:
    configure_logging()
    log = get_logger("pilot.007")

    # Range 2025-2026 for both (15 months — enough sample, manageable runtime)
    log.info("loading_nq")
    nq_bars = load_cme_csv(
        REPO_ROOT / "data" / "cme_nq_2021_2026" / "datos_cme.csv",
        family="MNQ", start=date(2025, 1, 1),
    )
    log.info("loading_es")
    es_bars = load_cme_csv(
        REPO_ROOT / "data" / "cme_es_2021_2026" /
        "glbx-mdp3-20210325-20260621.ohlcv-1m.csv",
        family="ES", start=date(2025, 1, 1),
    )

    nq = _run_full_period("MNQ (current prod)", nq_bars, MNQ_SPEC, log)
    es = _run_full_period("ES with MES economy", es_bars, MES_SPEC, log)

    common = nq["_trade_days"] & es["_trade_days"]
    union = nq["_trade_days"] | es["_trade_days"]
    overlap_pct = round(100 * len(common) / max(1, len(union)), 1)
    nq.pop("_trade_days")
    es.pop("_trade_days")

    run_id = datetime.now().strftime("%Y%m%dT%H%M%S")
    out_dir = REPO_ROOT / "reports" / "pilots" / f"pilot_007_{run_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(json.dumps(
        {"nq": nq, "es": es,
         "calendar_overlap_pct": overlap_pct,
         "n_common_days": len(common),
         "n_union_days": len(union)},
        indent=2, default=str,
    ))

    print("\n=== PILOT 007 — ES (MES economy) vs MNQ ===\n")
    keys = [
        ("trades", "trades"),
        ("trades_per_day", "tr/day"),
        ("win_rate", "WR"),
        ("expectancy_r", "exp R"),
        ("expectancy_usd", "exp $"),
        ("pnl_usd", "PnL $"),
        ("max_dd_pct", "MaxDD"),
        ("worst_trade", "worst trade $"),
        ("max_consec_losers", "max consec L"),
        ("boot_p95_dd_pct", "p95 DD"),
        ("boot_prob_profit", "P(profit)"),
    ]
    print(f"{'metric':<22} {'MNQ (prod)':>15} {'ES (MES econ)':>17}")
    print("-" * 56)
    for key, label in keys:
        nv = nq[key]
        ev = es[key]
        if "pct" in key or key in ("win_rate", "boot_prob_profit"):
            print(f"{label:<22} {nv:>14.2%}  {ev:>16.2%}")
        elif isinstance(nv, float):
            print(f"{label:<22} {nv:>14,.2f}  {ev:>16,.2f}")
        else:
            print(f"{label:<22} {nv:>14}  {ev:>16}")
    print(f"\nCalendar-day overlap (both traded same NY date): "
          f"{len(common)}/{len(union)} = {overlap_pct}%")
    print(f"\nArtifacts: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
