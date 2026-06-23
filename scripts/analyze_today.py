"""Post-mortem: what would the live config have done on a given NY date?

Fetches OHLCV from http://localhost:8080/backtest/ (already includes the
running day's data), filters to the requested NY date, runs the full
production pipeline (mode B Silver Bullet only, 1m, fixed_tp_r=1.5), and
reports every signal + which gate accepted/rejected it.

Defaults to "today (NY)" but accepts --date YYYY-MM-DD.

Usage:
    python scripts/analyze_today.py
    python scripts/analyze_today.py --date 2026-06-22
"""

from __future__ import annotations

import argparse
import io
import sys
from datetime import date as dtdate
from datetime import datetime

from ict_bot.backtest.engine import BacktestConfig, run_backtest
from ict_bot.backtest.runner import PipelineConfig, detect_all_signals
from ict_bot.data.loaders.ohlcv_http import fetch_ohlcv_1m
from ict_bot.reporting.metrics import compute_metrics
from ict_bot.risk.sizing import InstrumentSpec, RiskConfig
from ict_bot.sessions.killzones import SessionsConfig
from ict_bot.sessions.sessions import session_tag_at
from ict_bot.signals.imbalance.fvg import FVGConfig
from ict_bot.signals.setups.mss_fvg import MssFvgConfig
from ict_bot.signals.setups.ob_ote import ObOteConfig
from ict_bot.signals.setups.silver_bullet import SilverBulletConfig
from ict_bot.signals.setups.unicorn import UnicornConfig
from ict_bot.structure.displacement import DisplacementConfig
from ict_bot.utils.logging import configure_logging, get_logger
from ict_bot.utils.tz import NY, to_ny

if isinstance(sys.stdout, io.TextIOWrapper):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

# Production cell — must match configs/lucid_propfirm.yaml
PROD = {"body_atr_min": 1.0, "body_range_min": 0.5, "fixed_tp_r": 1.5}
MNQ_SPEC = InstrumentSpec(tick_size=0.25, tick_value_usd=0.50, point_value_usd=2.0)


def main() -> int:
    p = argparse.ArgumentParser(description="Post-mortem analyzer")
    p.add_argument("--date", default=None,
                   help="NY date YYYY-MM-DD (default: today NY)")
    p.add_argument("--qty", type=int, default=2,
                   help="contracts per trade (matches your live max_quantity)")
    args = p.parse_args()

    configure_logging()
    log = get_logger("analyze_today")
    log.info("fetching_ohlcv")
    bars_all = fetch_ohlcv_1m(use_cache=False, refresh=True)
    target = (
        dtdate.fromisoformat(args.date) if args.date
        else to_ny(datetime.now(tz=NY)).date()
    )
    log.info("target_date", date=str(target))

    day = bars_all.df.filter(bars_all.df["ts_ny"].dt.date() == target)
    if day.is_empty():
        log.error("no_bars_for_date", date=str(target))
        return 1
    from ict_bot.data.models import Bars
    day_bars = Bars(df=day, tf="1m", symbol=bars_all.symbol)

    print(f"\n=== Post-mortem analysis — NY date {target} ===")
    print(f"Source: http://localhost:8080/backtest/  (OHLCV 1m)")
    print(f"Bars today: {len(day_bars)}  "
          f"first={day_bars.first_ts()}  last={day_bars.last_ts()}")
    print(f"Cell: body_atr={PROD['body_atr_min']}, body_range={PROD['body_range_min']}, "
          f"fixed_tp_r={PROD['fixed_tp_r']}, qty={args.qty}\n")

    pcfg = PipelineConfig(
        displacement=DisplacementConfig(
            atr_lookback=14,
            body_atr_min=PROD["body_atr_min"],
            body_range_min=PROD["body_range_min"],
        ),
        fvg=FVGConfig(require_displacement=True, min_gap_ticks=1, tick_size=0.25),
        unicorn=UnicornConfig(min_rr=1.0, tp_strategy="fixed_R",
                               fixed_tp_r=PROD["fixed_tp_r"]),
        mss_fvg=MssFvgConfig(min_rr=1.0, tp_strategy="fixed_R",
                              fixed_tp_r=PROD["fixed_tp_r"]),
        ob_ote=ObOteConfig(min_rr=1.0, tp_strategy="fixed_R",
                            fixed_tp_r=PROD["fixed_tp_r"]),
        silver_bullet=SilverBulletConfig(min_rr=1.0, tp_strategy="fixed_R",
                                          fixed_tp_r=PROD["fixed_tp_r"]),
    )
    sess = SessionsConfig(
        allowed_windows=("silver_bullet_am", "silver_bullet_pm"),
    )
    bcfg = BacktestConfig(
        starting_equity=25_000.0,
        enforce_killzones=True,
        enforce_midnight_filter=True,
        enforce_force_flat=True,
    )

    signals = detect_all_signals(day_bars, cfg=pcfg)
    print(f"Signals detected (any window): {len(signals)}")
    by_tag: dict[str, int] = {}
    for s in signals:
        tag = session_tag_at(s.ts_ny, sess)
        by_tag[tag] = by_tag.get(tag, 0) + 1
    for tag, n in sorted(by_tag.items(), key=lambda kv: -kv[1]):
        print(f"  {tag:<25} {n}")

    # Match the live risk config: max_quantity matches user's --qty arg
    risk = RiskConfig(per_trade_risk_pct=0.24, max_quantity=args.qty, min_quantity=1)
    result = run_backtest(day_bars, signals, config=bcfg, sessions=sess,
                          instrument=MNQ_SPEC, risk=risk)
    m = compute_metrics(result.portfolio)

    print(f"\n=== Trades executed (Silver Bullet windows only, qty={args.qty}) ===")
    if m.n_trades == 0:
        print("No trades today.")
        print(f"Skip reasons: {result.reasons_skipped}")
        return 0

    for t in result.portfolio.trades:
        outcome = "TP" if t.pnl_usd > 0 else "SL"
        print(
            f"  {t.entry_ts_ny.strftime('%H:%M')} "
            f"{t.setup_name:<14} {t.side:<5} "
            f"entry={t.entry_price:.2f} SL={t.stop_loss:.2f} TP={t.take_profit:.2f} "
            f"→ {outcome} pnl=${t.pnl_usd:+.2f}",
        )

    print(f"\n=== Day summary ===")
    print(f"Trades:       {m.n_trades}")
    print(f"Win rate:     {m.win_rate:.0%}")
    print(f"PnL:          ${m.total_pnl_usd:+,.2f}")
    print(f"Max DD:       ${m.max_drawdown_usd:,.2f} ({m.max_drawdown_pct:.2%})")
    print(f"Skip reasons: {result.reasons_skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
