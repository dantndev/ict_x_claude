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


def bars_from_ticks(
    ticks_df: pl.DataFrame,
    *,
    symbol: str,
    target_tf: Timeframe = "1m",
    price_col: str = "best_bid",
    volume_col: str | None = "fp_trade_count",
) -> Bars:
    """Build OHLCV Bars from an L2 ticks DataFrame.

    Uses the mid (or `price_col`) of each tick to form OHLC. Volume comes from
    `volume_col` if available (e.g., `fp_trade_count`); otherwise counts ticks.
    Result is sorted and timezone-aware on `ts_ny`.
    """
    if ticks_df.is_empty():
        return Bars(
            df=pl.DataFrame(
                schema={
                    "ts_ny": pl.Datetime,
                    "open": pl.Float64,
                    "high": pl.Float64,
                    "low": pl.Float64,
                    "close": pl.Float64,
                    "volume": pl.Int64,
                },
            ),
            tf=target_tf,
            symbol=symbol,
        )
    every = _TF_TO_POLARS[target_tf]
    # Build a "mid" if we have bid+ask, else use price_col directly
    if "best_bid" in ticks_df.columns and "best_ask" in ticks_df.columns:
        df = ticks_df.with_columns(
            ((pl.col("best_bid") + pl.col("best_ask")) / 2.0).alias("_price"),
        )
    else:
        df = ticks_df.rename({price_col: "_price"})
    if volume_col is not None and volume_col in df.columns:
        vol_expr = pl.col(volume_col).sum().cast(pl.Int64).alias("volume")
    else:
        vol_expr = pl.len().cast(pl.Int64).alias("volume")
    agg = [
        pl.col("_price").first().alias("open"),
        pl.col("_price").max().alias("high"),
        pl.col("_price").min().alias("low"),
        pl.col("_price").last().alias("close"),
        vol_expr,
    ]
    out = (
        df.sort("ts_ny")
        .group_by_dynamic(
            index_column="ts_ny", every=every, closed="left", label="left",
        )
        .agg(agg)
    )
    return Bars(df=out, tf=target_tf, symbol=symbol)
