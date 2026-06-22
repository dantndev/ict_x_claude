"""PILOT 008 (FULL) — MGC vs MNQ over 15 months + calendar overlap.

Smoke test (pilot_008_gold_smoke.py) passed: gold's natural SL averages
~3 pts = ~$30/contract on MGC, identical to MNQ's risk budget, so dual
operation is mechanically feasible. This script runs the full 15-month
window (matching pilot 007's range) and reports calendar overlap with
MNQ trades — the key metric for "true diversification vs hidden leverage".
"""

from __future__ import annotations

import io
import json
import sys
import time
from datetime import date, datetime
from statistics import fmean

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
MGC_SPEC = InstrumentSpec(tick_size=0.10, tick_value_usd=1.00, point_value_usd=10.0)
MNQ_SPEC = InstrumentSpec(tick_size=0.25, tick_value_usd=0.50, point_value_usd=2.0)


def _pcfg(tick_size: float) -> PipelineConfig:
    return PipelineConfig(
        displacement=DisplacementConfig(
            atr_lookback=14,
            body_atr_min=WINNER["body_atr_min"],
            body_range_min=WINNER["body_range_min"],
        ),
        fvg=FVGConfig(require_displacement=True, min_gap_ticks=1, tick_size=tick_size),
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


def _summarize(name: str, bars, instrument: InstrumentSpec,
                tick_size: float, log) -> dict:
    t0 = time.time()
    sess = SessionsConfig(allowed_windows=("silver_bullet_am", "silver_bullet_pm"))
    bcfg = BacktestConfig(enforce_killzones=True, enforce_midnight_filter=True)
    pcfg = _pcfg(tick_size)
    n_days = max(1, (bars.last_ts() - bars.first_ts()).days)  # type: ignore[operator]
    log.info(f"{name}_start", bars=len(bars), n_days=n_days)

    signals = detect_all_signals(bars, cfg=pcfg)
    log.info(f"{name}_signals", count=len(signals),
             elapsed_s=round(time.time() - t0, 1))

    result = run_backtest(bars, signals, config=bcfg, sessions=sess,
                          instrument=instrument)
    m = compute_metrics(result.portfolio)
    boot = bootstrap_stats(result.portfolio, iterations=1000)
    sls = [abs(t.entry_price - t.stop_loss) for t in result.portfolio.trades]
    sl_usd = [d * instrument.point_value_usd for d in sls]
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
        "max_dd_pct": round(m.max_drawdown_pct, 4),
        "worst_trade": round(
            min((t.pnl_usd for t in result.portfolio.trades), default=0.0), 2,
        ),
        "max_consec_losers": _max_consec_losses(result.portfolio.trades),
        "boot_p95_dd_pct": round(boot.max_dd_p95_pct, 4),
        "boot_prob_profit": round(boot.prob_profitable, 3),
        "mean_sl_pts": round(fmean(sls), 3) if sls else 0.0,
        "mean_sl_usd": round(fmean(sl_usd), 2) if sl_usd else 0.0,
        "_trade_days": {t.entry_ts_ny.strftime("%Y-%m-%d")
                         for t in result.portfolio.trades},
        "_trade_day_pnl": {
            t.entry_ts_ny.strftime("%Y-%m-%d"): t.pnl_usd
            for t in result.portfolio.trades
        },
    }


def main() -> int:
    configure_logging()
    log = get_logger("pilot.008.full")

    log.info("loading_nq")
    nq_bars = load_cme_csv(
        REPO_ROOT / "data" / "cme_nq_2021_2026" / "datos_cme.csv",
        family="MNQ", start=date(2025, 1, 1),
    )
    log.info("loading_mgc")
    mgc_bars = load_cme_csv(
        REPO_ROOT / "data" / "cme_mcg_2021_2026" /
        "glbx-mdp3-20210325-20260621.ohlcv-1m (1).csv",
        family="MGC", start=date(2025, 1, 1),
    )

    nq = _summarize("MNQ (current prod)", nq_bars, MNQ_SPEC, 0.25, log)
    mgc = _summarize("MGC (gold)", mgc_bars, MGC_SPEC, 0.10, log)

    common = nq["_trade_days"] & mgc["_trade_days"]
    union = nq["_trade_days"] | mgc["_trade_days"]
    overlap_pct = round(100 * len(common) / max(1, len(union)), 1)

    # Day-PnL correlation on overlapping days (proxy for "they tend to
    # win/lose together"). Computed only over days both traded.
    if common:
        nq_daily = {}
        mgc_daily = {}
        for d in common:
            nq_daily[d] = sum(p for k, p in nq["_trade_day_pnl"].items() if k == d)
            mgc_daily[d] = sum(p for k, p in mgc["_trade_day_pnl"].items() if k == d)
        # Compute correlation
        n = len(common)
        sum_x = sum(nq_daily.values())
        sum_y = sum(mgc_daily.values())
        mean_x = sum_x / n
        mean_y = sum_y / n
        num = sum((nq_daily[d] - mean_x) * (mgc_daily[d] - mean_y) for d in common)
        den_x = (sum((nq_daily[d] - mean_x) ** 2 for d in common)) ** 0.5
        den_y = (sum((mgc_daily[d] - mean_y) ** 2 for d in common)) ** 0.5
        corr = round(num / (den_x * den_y), 3) if den_x > 0 and den_y > 0 else 0.0
    else:
        corr = 0.0

    nq.pop("_trade_days")
    nq.pop("_trade_day_pnl")
    mgc.pop("_trade_days")
    mgc.pop("_trade_day_pnl")

    run_id = datetime.now().strftime("%Y%m%dT%H%M%S")
    out_dir = REPO_ROOT / "reports" / "pilots" / f"pilot_008_full_{run_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(json.dumps({
        "nq": nq, "mgc": mgc,
        "calendar_overlap_pct": overlap_pct,
        "n_common_days": len(common),
        "n_union_days": len(union),
        "same_day_pnl_correlation": corr,
    }, indent=2, default=str))

    print("\n=== PILOT 008 FULL — MGC (gold) vs MNQ over 15 months ===\n")
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
        ("mean_sl_pts", "mean SL pts"),
        ("mean_sl_usd", "mean SL $/ct"),
    ]
    print(f"{'metric':<22} {'MNQ':>15} {'MGC':>15}")
    print("-" * 54)
    for key, label in keys:
        nv = nq[key]
        mv = mgc[key]
        if "pct" in key or key in ("win_rate", "boot_prob_profit"):
            print(f"{label:<22} {nv:>14.2%}  {mv:>14.2%}")
        elif isinstance(nv, float):
            print(f"{label:<22} {nv:>14,.2f}  {mv:>14,.2f}")
        else:
            print(f"{label:<22} {nv:>14}  {mv:>14}")
    print(f"\nCalendar overlap (both traded same NY day): "
          f"{len(common)}/{len(union)} = {overlap_pct}%")
    print(f"Same-day PnL correlation on overlapping days: {corr}")
    print(f"\nArtifacts: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
