"""Domain models for market data.

Bars  — OHLCV time series, one row per candle, NY-localized timestamps.
Ticks — L2 microstructure stream, one row per tick (sub-second), NY-localized.

Internally both wrap a Polars DataFrame with a known schema. Users interact
through typed accessors; raw column manipulation is allowed (it's just polars)
but discouraged outside the data layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar, Final, Literal, cast

import polars as pl

# ───────────────────────────── Bars ─────────────────────────────

Timeframe = Literal["1m", "3m", "5m", "15m", "1H", "4H", "1D"]

TF_MINUTES: Final[dict[Timeframe, int]] = {
    "1m": 1, "3m": 3, "5m": 5, "15m": 15, "1H": 60, "4H": 240, "1D": 1440,
}


@dataclass(frozen=True, slots=True)
class Bars:
    """Wrapper around a Polars DataFrame holding OHLCV bars in NY time.

    Schema (required columns):
        ts_ny       — Datetime[ns, America/New_York]  (bar open time)
        open, high, low, close  — Float64
        volume      — Int64
    Optional columns:
        bid_vol, ask_vol, delta — Int64 (footprint, when available)
        symbol      — Utf8
        tf          — Utf8  (one of TF_MINUTES keys; if absent assumed from constructor)
    """

    df: pl.DataFrame
    tf: Timeframe
    symbol: str

    REQUIRED_COLS: ClassVar[tuple[str, ...]] = (
        "ts_ny", "open", "high", "low", "close", "volume",
    )

    def __post_init__(self) -> None:
        missing = [c for c in self.REQUIRED_COLS if c not in self.df.columns]
        if missing:
            raise ValueError(f"Bars missing required columns: {missing}")
        if self.tf not in TF_MINUTES:
            raise ValueError(f"Unknown timeframe {self.tf!r}")

    def __len__(self) -> int:
        return self.df.height

    @property
    def empty(self) -> bool:
        return self.df.is_empty()

    def first_ts(self) -> datetime | None:
        if self.empty:
            return None
        return cast("datetime", self.df["ts_ny"][0])

    def last_ts(self) -> datetime | None:
        if self.empty:
            return None
        return cast("datetime", self.df["ts_ny"][-1])

    def slice(self, start: datetime | None = None, end: datetime | None = None) -> Bars:
        """Return a sub-range of bars by inclusive timestamps."""
        df = self.df
        if start is not None:
            df = df.filter(pl.col("ts_ny") >= start)
        if end is not None:
            df = df.filter(pl.col("ts_ny") <= end)
        return Bars(df=df, tf=self.tf, symbol=self.symbol)

    def to_dicts(self) -> list[dict[str, object]]:
        return self.df.to_dicts()


# ───────────────────────────── Ticks ─────────────────────────────

@dataclass(frozen=True, slots=True)
class Ticks:
    """Wrapper around a Polars DataFrame of L2 / microstructure ticks.

    Schema (from Data_Historica_L2_V2/*.csv after normalization):
        ts_ny                 — Datetime[ns, America/New_York]   (canonical clock)
        ts_utc                — Datetime[ns, UTC]                (preserved for audit)
        symbol                — Utf8
        best_bid, best_ask    — Float64
        spread_pts            — Float64
        spread_avg_30s        — Float64
        spread_compression    — Float64
        bid_top10_total, ask_top10_total — Int64
        obi_top10             — Float64
        fp_bid_vol, fp_ask_vol, fp_delta, fp_trade_count — Int64
        tick_count_5s, price_changes_5s — Int64
        tick_velocity         — Float64
        delta_5s_reciente, delta_5s_anterior, delta_acceleration — Float64
        trades_per_sec_runtime — Float64
        recepcion_ms          — Float64
    """

    df: pl.DataFrame
    symbol: str

    REQUIRED_COLS: ClassVar[tuple[str, ...]] = (
        "ts_ny", "ts_utc", "symbol", "best_bid", "best_ask",
        "spread_pts", "obi_top10", "fp_delta",
    )

    def __post_init__(self) -> None:
        missing = [c for c in self.REQUIRED_COLS if c not in self.df.columns]
        if missing:
            raise ValueError(f"Ticks missing required columns: {missing}")

    def __len__(self) -> int:
        return self.df.height

    @property
    def empty(self) -> bool:
        return self.df.is_empty()

    def slice(self, start: datetime | None = None, end: datetime | None = None) -> Ticks:
        df = self.df
        if start is not None:
            df = df.filter(pl.col("ts_ny") >= start)
        if end is not None:
            df = df.filter(pl.col("ts_ny") <= end)
        return Ticks(df=df, symbol=self.symbol)
