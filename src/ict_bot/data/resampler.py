"""Resample 1-minute Bars to higher timeframes.

Aggregation rules (canonical OHLCV):
    open   = first
    high   = max
    low    = min
    close  = last
    volume = sum
    bid_vol, ask_vol, fp_trade_count — sum (when present)
    delta  = sum (when present; equivalent to ask_vol - bid_vol)

Each resampled bar's ts_ny is its OPEN time (left-closed buckets).
"""

from __future__ import annotations

import polars as pl

from ict_bot.data.models import TF_MINUTES, Bars, Timeframe

_TF_TO_POLARS: dict[Timeframe, str] = {
    "1m": "1m", "3m": "3m", "5m": "5m", "15m": "15m",
    "1H": "1h", "4H": "4h", "1D": "1d",
}


def resample(bars: Bars, target_tf: Timeframe) -> Bars:
    """Resample to a higher (or equal) timeframe.

    Raises:
        ValueError if target_tf is finer than source.
    """
    if target_tf == bars.tf:
        return bars
    if TF_MINUTES[target_tf] < TF_MINUTES[bars.tf]:
        raise ValueError(
            f"Cannot resample finer: source={bars.tf}, target={target_tf}",
        )

    every = _TF_TO_POLARS[target_tf]

    agg_exprs: list[pl.Expr] = [
        pl.col("open").first().alias("open"),
        pl.col("high").max().alias("high"),
        pl.col("low").min().alias("low"),
        pl.col("close").last().alias("close"),
        pl.col("volume").sum().alias("volume"),
    ]
    opt_sum_cols = ("bid_vol", "ask_vol", "fp_trade_count", "delta")
    for c in opt_sum_cols:
        if c in bars.df.columns:
            agg_exprs.append(pl.col(c).sum().alias(c))

    out = (
        bars.df
        .sort("ts_ny")
        .group_by_dynamic(
            index_column="ts_ny",
            every=every,
            closed="left",
            label="left",
        )
        .agg(agg_exprs)
    )
    return Bars(df=out, tf=target_tf, symbol=bars.symbol)
