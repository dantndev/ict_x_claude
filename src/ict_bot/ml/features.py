"""Feature extraction for a single Signal: combines setup metadata with L2
microstructure aggregates over a short window around the entry timestamp.

When `ticks` is None or empty, microstructure features default to zero — the
model can still train on setup-only features (useful when L2 isn't available
for a given range).
"""

from __future__ import annotations

from datetime import timedelta

from ict_bot.data.models import Bars, Ticks
from ict_bot.signals.setups.base import Signal


def features_for_signal(
    sig: Signal,
    ticks: Ticks | None,
    bars: Bars,
) -> dict[str, float]:
    """Return a flat numeric dict of features for ML."""
    f: dict[str, float] = {
        "setup_unicorn": 1.0 if sig.setup_name == "unicorn" else 0.0,
        "setup_mss_fvg": 1.0 if sig.setup_name == "mss_fvg" else 0.0,
        "setup_ob_ote": 1.0 if sig.setup_name == "ob_ote" else 0.0,
        "setup_silver_bullet": 1.0 if sig.setup_name == "silver_bullet" else 0.0,
        "side_buy": 1.0 if sig.side == "BUY" else 0.0,
        "rr": sig.rr,
        "risk_pts": sig.risk,
        "reward_pts": sig.reward,
        "confidence": sig.confidence,
        "in_killzone": 1.0 if sig.in_killzone else 0.0,
        "htf_anchored": 1.0 if sig.htf_anchored else 0.0,
        "midnight_filter_ok": 1.0 if sig.midnight_filter_ok else 0.0,
        "hour": float(sig.ts_ny.hour),
        "weekday": float(sig.ts_ny.weekday()),
    }
    # Bar context: ATR proxy = mean range over prior 14 bars at sig.bar_index
    if not bars.empty and sig.bar_index >= 14:
        sub = bars.df.slice(sig.bar_index - 14, 14)
        ranges = (sub["high"] - sub["low"]).to_list()
        f["atr14"] = float(sum(ranges) / len(ranges)) if ranges else 0.0
    else:
        f["atr14"] = 0.0

    # L2 microstructure: aggregates over a ±60s window around sig.ts_ny
    if ticks is not None and not ticks.empty:
        window_start = sig.ts_ny - timedelta(seconds=60)
        window_end = sig.ts_ny + timedelta(seconds=60)
        sub_t = ticks.slice(start=window_start, end=window_end)
        if not sub_t.empty:
            df = sub_t.df

            def _mean_or_zero(col: str) -> float:
                if col not in df.columns:
                    return 0.0
                m = df[col].mean()
                return float(m) if m is not None else 0.0  # type: ignore[arg-type]

            f["l2_fp_delta_mean"] = _mean_or_zero("fp_delta")
            f["l2_obi_mean"] = _mean_or_zero("obi_top10")
            f["l2_spread_mean"] = _mean_or_zero("spread_pts")
            f["l2_delta_accel_mean"] = _mean_or_zero("delta_acceleration")
            f["l2_spread_compression_mean"] = _mean_or_zero("spread_compression")
        else:
            f.update({
                "l2_fp_delta_mean": 0.0, "l2_obi_mean": 0.0,
                "l2_spread_mean": 0.0, "l2_delta_accel_mean": 0.0,
                "l2_spread_compression_mean": 0.0,
            })
    else:
        f.update({
            "l2_fp_delta_mean": 0.0, "l2_obi_mean": 0.0,
            "l2_spread_mean": 0.0, "l2_delta_accel_mean": 0.0,
            "l2_spread_compression_mean": 0.0,
        })
    return f


FEATURE_KEYS: tuple[str, ...] = (
    "setup_unicorn", "setup_mss_fvg", "setup_ob_ote", "setup_silver_bullet",
    "side_buy", "rr", "risk_pts", "reward_pts", "confidence",
    "in_killzone", "htf_anchored", "midnight_filter_ok",
    "hour", "weekday", "atr14",
    "l2_fp_delta_mean", "l2_obi_mean", "l2_spread_mean",
    "l2_delta_accel_mean", "l2_spread_compression_mean",
)


def features_to_vector(f: dict[str, float]) -> list[float]:
    return [f.get(k, 0.0) for k in FEATURE_KEYS]
