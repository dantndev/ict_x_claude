"""OHLCV loader for the local backtest HTTP API.

Endpoint (default `http://localhost:8080/backtest/`) returns a single JSON array
of 1-minute bars for the NQ. Schema observed:

    [
      {"time": "2026-03-22 18:00:00.000",
       "open": 24188.25, "high": 24188.25, "low": 24158.5, "close": 24165,
       "volume": 6, "bid_vol": 0, "ask_vol": 0, "delta": 0},
      ...
    ]

The endpoint ignores query parameters; the entire dataset is returned. Timestamps
are NY local (consistent with the L2 CSVs' `ts_ny` column).

This loader:
- Fetches once and caches as parquet under data/cache/ohlcv_1m_<symbol>.parquet.
- Returns a `Bars(tf="1m")` ready for downstream use.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import polars as pl

from ict_bot.config.settings import REPO_ROOT, get_settings
from ict_bot.data.cache import ohlcv_cache_path, read_parquet, write_parquet
from ict_bot.data.models import Bars
from ict_bot.utils.logging import get_logger
from ict_bot.utils.tz import NY

log = get_logger(__name__)


def fetch_ohlcv_1m(
    *,
    url: str | None = None,
    symbol: str | None = None,
    use_cache: bool = True,
    refresh: bool = False,
    timeout_s: float = 30.0,
    repo_root: Path = REPO_ROOT,
) -> Bars:
    """Fetch 1-minute OHLCV from the backtest API and return Bars.

    Args:
        url: HTTP endpoint. Defaults to settings.ict_backtest_api_url.
        symbol: Symbol tag (used for cache filename). Defaults to settings.ict_symbol.
        use_cache: If True, prefer the local parquet cache when present.
        refresh: If True, ignore cache and re-fetch from the API.
        timeout_s: HTTP timeout.
        repo_root: Repo root path (used to locate the cache dir).
    """
    settings = get_settings()
    url = url or settings.ict_backtest_api_url
    symbol = symbol or settings.ict_symbol
    cache_path = ohlcv_cache_path(repo_root, symbol=symbol, tf="1m")

    if use_cache and not refresh:
        cached = read_parquet(cache_path)
        if cached is not None:
            log.info("ohlcv_cache_hit", path=str(cache_path), rows=cached.height)
            return Bars(df=cached, tf="1m", symbol=symbol)

    log.info("ohlcv_fetch_start", url=url)
    with httpx.Client(timeout=timeout_s) as client:
        resp = client.get(url)
        resp.raise_for_status()
        payload = resp.json()
    log.info("ohlcv_fetch_done", rows=len(payload))

    df = _payload_to_df(payload, symbol=symbol)
    write_parquet(df, cache_path)
    return Bars(df=df, tf="1m", symbol=symbol)


def _payload_to_df(payload: list[dict[str, object]], *, symbol: str) -> pl.DataFrame:
    """Normalize the JSON payload into the canonical Bars schema."""
    df = pl.DataFrame(payload)
    # Parse the `time` string as a naive datetime, then localize to NY.
    df = df.with_columns(
        pl.col("time")
        .str.to_datetime(format="%Y-%m-%d %H:%M:%S%.f", time_unit="us", strict=False)
        .dt.replace_time_zone(NY.key)
        .alias("ts_ny"),
    ).drop("time")

    # Enforce column dtypes (use class objects; polars accepts them in .cast())
    casts: dict[str, type[pl.DataType]] = {
        "open": pl.Float64, "high": pl.Float64, "low": pl.Float64, "close": pl.Float64,
        "volume": pl.Int64,
    }
    for c in ("bid_vol", "ask_vol", "delta"):
        if c in df.columns:
            casts[c] = pl.Int64
    df = df.with_columns([pl.col(c).cast(t) for c, t in casts.items()])

    df = df.with_columns(pl.lit(symbol).alias("symbol"))

    # Drop any rows with malformed timestamps and sort.
    df = df.drop_nulls("ts_ny").sort("ts_ny").unique(subset=["ts_ny"], keep="first")
    return df
