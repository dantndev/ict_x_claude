"""PILOT 008 (SMOKE) — Validate the production cell on MGC, 1-month test.

Gold may have a fundamentally different SL distance than NQ because the
volatility per point is much smaller (gold trades at $2-4k vs NQ $20k).
Before committing to a full backtest, smoke-test on 1 month and report:

  1. Average SL distance produced by the bot in points and USD per
     contract — confirms whether MGC is operable for the $25k account.
  2. Trade count, win rate, expectancy R / USD on a small sample.
  3. The CSV-loader path works for `family='MGC'` (6 quarterly months
     per year G/J/M/Q/V/Z, different from NQ/ES).

If SL/contract <= $80 and expectancy_R > 0.5, run the full 15-month
follow-up. Otherwise abort with a clean reason.
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

if isinstance(sys.stdout, io.TextIOWrapper):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]


WINNER = {"body_atr_min": 1.0, "body_range_min": 0.5, "fixed_tp_r": 1.5}
MGC_SPEC = InstrumentSpec(tick_size=0.10, tick_value_usd=1.00, point_value_usd=10.0)


def _pcfg() -> PipelineConfig:
    return PipelineConfig(
        displacement=DisplacementConfig(
            atr_lookback=14,
            body_atr_min=WINNER["body_atr_min"],
            body_range_min=WINNER["body_range_min"],
        ),
        fvg=FVGConfig(require_displacement=True, min_gap_ticks=1, tick_size=0.10),
        unicorn=UnicornConfig(min_rr=1.0, tp_strategy="fixed_R",
                               fixed_tp_r=WINNER["fixed_tp_r"]),
        mss_fvg=MssFvgConfig(min_rr=1.0, tp_strategy="fixed_R",
                              fixed_tp_r=WINNER["fixed_tp_r"]),
        ob_ote=ObOteConfig(min_rr=1.0, tp_strategy="fixed_R",
                            fixed_tp_r=WINNER["fixed_tp_r"]),
        silver_bullet=SilverBulletConfig(min_rr=1.0, tp_strategy="fixed_R",
                                          fixed_tp_r=WINNER["fixed_tp_r"]),
    )


def main() -> int:
    configure_logging()
    log = get_logger("pilot.008.smoke")

    t0 = time.time()
    log.info("loading_mgc")
    mgc = load_cme_csv(
        REPO_ROOT / "data" / "cme_mcg_2021_2026" /
        "glbx-mdp3-20210325-20260621.ohlcv-1m (1).csv",
        family="MGC", start=date(2026, 1, 1),
    )
    log.info("mgc_loaded", bars=len(mgc),
             first=str(mgc.first_ts()), last=str(mgc.last_ts()),
             elapsed_s=round(time.time() - t0, 1))

    sess = SessionsConfig(allowed_windows=("silver_bullet_am", "silver_bullet_pm"))
    bcfg = BacktestConfig(enforce_killzones=True, enforce_midnight_filter=True)
    pcfg = _pcfg()

    t1 = time.time()
    signals = detect_all_signals(mgc, cfg=pcfg)
    log.info("signals_ready", count=len(signals),
             elapsed_s=round(time.time() - t1, 1))

    result = run_backtest(mgc, signals, config=bcfg, sessions=sess,
                          instrument=MGC_SPEC)
    m = compute_metrics(result.portfolio)

    # SL stats — the key question for operability
    sl_distances_pts = [
        abs(t.entry_price - t.stop_loss) for t in result.portfolio.trades
    ]
    sl_distances_usd = [d * MGC_SPEC.point_value_usd for d in sl_distances_pts]

    print("\n=== PILOT 008 SMOKE — MGC over Jan 2026 + (this month) ===\n")
    print(f"Bars: {len(mgc)}")
    print(f"Date range: {mgc.first_ts()} -> {mgc.last_ts()}")
    print(f"Signals detected: {len(signals)}")
    print(f"Trades executed: {m.n_trades}")
    if m.n_trades == 0:
        print("\n>>> NO TRADES — cell does not produce signals in MGC at all. <<<")
        print(">>> Likely cause: thresholds tuned to NQ tick size (0.25 pt) "
              "don't carry to MGC (0.10 pt). Aborting full pilot. <<<")
        return 0
    print(f"Win rate: {m.win_rate:.1%}")
    print(f"Expectancy: ${m.expectancy_usd:,.2f} / {m.expectancy_r:+.2f} R")
    print(f"Total PnL: ${m.total_pnl_usd:,.2f}")
    print(f"\nSL distance per contract:")
    print(f"  mean: {fmean(sl_distances_pts):.2f} pts  ${fmean(sl_distances_usd):.2f}")
    print(f"  max:  {max(sl_distances_pts):.2f} pts  ${max(sl_distances_usd):.2f}")
    print(f"  min:  {min(sl_distances_pts):.2f} pts  ${min(sl_distances_usd):.2f}")
    print(f"\nFor a $25k account with $1k DD:")
    print(f"  - $1k DD / mean SL = {1000 / fmean(sl_distances_usd):.1f} max consecutive "
          f"full-stops at 1 micro")
    print(f"  - 0.24% of $25k = $60 risk budget. With mean SL of "
          f"${fmean(sl_distances_usd):.0f}/contract, max qty = "
          f"{int(60 / fmean(sl_distances_usd))} micros")

    decision = "PROCEED" if (m.expectancy_r > 0.5 and
                              fmean(sl_distances_usd) <= 80) else "ABORT"
    print(f"\n>>> DECISION: {decision} <<<")
    if decision == "PROCEED":
        print(">>> Smoke OK — run the full 15-month follow-up "
              "(pilot 008 full). <<<")
    else:
        reason = []
        if m.expectancy_r <= 0.5:
            reason.append(f"expectancy_r={m.expectancy_r:.2f} <= 0.5")
        if fmean(sl_distances_usd) > 80:
            reason.append(f"mean SL ${fmean(sl_distances_usd):.0f} > $80/contract")
        print(f">>> Reason(s): {', '.join(reason)} <<<")

    out = {
        "n_bars": len(mgc),
        "n_trades": m.n_trades,
        "win_rate": round(m.win_rate, 3),
        "expectancy_r": round(m.expectancy_r, 3),
        "expectancy_usd": round(m.expectancy_usd, 2),
        "pnl_usd": round(m.total_pnl_usd, 2),
        "mean_sl_pts": round(fmean(sl_distances_pts), 3),
        "mean_sl_usd_per_contract": round(fmean(sl_distances_usd), 2),
        "max_sl_pts": round(max(sl_distances_pts), 3),
        "min_sl_pts": round(min(sl_distances_pts), 3),
        "decision": decision,
    }
    run_id = datetime.now().strftime("%Y%m%dT%H%M%S")
    out_dir = REPO_ROOT / "reports" / "pilots" / f"pilot_008_smoke_{run_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "smoke.json").write_text(json.dumps(out, indent=2, default=str))
    print(f"\nArtifacts: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
