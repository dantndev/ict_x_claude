"""L2 tick loader for the Data_Historica_L2_V2 CSV corpus.

File layout (one CSV per trading day):
    l2_v2_YYYY-MM-DD.csv

Columns (from `head -1` of any file):
    ts_local, ts_ny, ts_utc, recepcion_ms, symbol,
    fp_window_ms, fp_bid_vol, fp_ask_vol, fp_delta, fp_trade_count,
    tick_count_5s, price_changes_5s, tick_velocity,
    delta_5s_reciente, delta_5s_anterior, delta_acceleration,
    best_bid, best_ask, spread_pts, spread_avg_30s, spread_compression,
    bid_top10_total, ask_top10_total, obi_top10, trades_per_sec_runtime

`ts_ny` arrives as a string `YYYY-MM-DD HH:MM:SS.fff` in NY local time;
we parse and tag it with the America/New_York timezone (no DST shift —
the producer already gives NY-local stamps).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl

from ict_bot.config.settings import REPO_ROOT, get_settings
from ict_bot.data.cache import l2_cache_path, read_parquet, write_parquet
from ict_bot.data.models import Ticks
from ict_bot.utils.logging import get_logger
from ict_bot.utils.tz import NY, UTC

log = get_logger(__name__)


def _csv_path(csv_dir: Path, day: date) -> Path:
    return csv_dir / f"l2_v2_{day.isoformat()}.csv"


def _parse_one_csv(path: Path, *, symbol: str) -> pl.DataFrame:
    df = pl.read_csv(
        path,
        try_parse_dates=False,
        infer_schema_length=10000,
    )
    df = df.with_columns(
        pl.col("ts_ny")
        .str.to_datetime(format="%Y-%m-%d %H:%M:%S%.f", time_unit="us", strict=False)
        .dt.replace_time_zone(NY.key)
        .alias("ts_ny"),
        pl.col("ts_utc")
        .str.to_datetime(format="%Y-%m-%d %H:%M:%S%.f", time_unit="us", strict=False)
        .dt.replace_time_zone(UTC.key)
        .alias("ts_utc"),
    )
    if "symbol" not in df.columns:
        df = df.with_columns(pl.lit(symbol).alias("symbol"))
    return df.drop_nulls("ts_ny").sort("ts_ny")


def load_day(
    day: date,
    *,
    csv_dir: Path | None = None,
    symbol: str | None = None,
    use_cache: bool = True,
    refresh: bool = False,
    repo_root: Path = REPO_ROOT,
) -> Ticks:
    """Load a single trading day of L2 ticks. Caches to parquet for future calls."""
    settings = get_settings()
    csv_dir = csv_dir or settings.ict_l2_csv_dir
    symbol = symbol or settings.ict_symbol

    cache = l2_cache_path(repo_root, symbol=symbol, day=day.isoformat())
    if use_cache and not refresh:
        cached = read_parquet(cache)
        if cached is not None:
            log.info("l2_cache_hit", day=day.isoformat(), rows=cached.height)
            return Ticks(df=cached, symbol=symbol)

    path = _csv_path(csv_dir, day)
    if not path.exists():
        raise FileNotFoundError(f"L2 CSV missing for {day.isoformat()}: {path}")

    log.info("l2_csv_parse_start", day=day.isoformat(), path=str(path))
    df = _parse_one_csv(path, symbol=symbol)
    log.info("l2_csv_parse_done", day=day.isoformat(), rows=df.height)
    write_parquet(df, cache)
    return Ticks(df=df, symbol=symbol)


def list_available_days(csv_dir: Path | None = None) -> list[date]:
    settings = get_settings()
    csv_dir = csv_dir or settings.ict_l2_csv_dir
    days: list[date] = []
    for p in sorted(csv_dir.glob("l2_v2_*.csv")):
        stem = p.stem.removeprefix("l2_v2_")
        try:
            days.append(date.fromisoformat(stem))
        except ValueError:
            continue
    return days


def load_range(
    start: date,
    end: date,
    *,
    csv_dir: Path | None = None,
    symbol: str | None = None,
    use_cache: bool = True,
) -> Ticks:
    """Load and concatenate L2 ticks across [start, end]. Missing days are skipped."""
    settings = get_settings()
    csv_dir = csv_dir or settings.ict_l2_csv_dir
    symbol = symbol or settings.ict_symbol

    frames: list[pl.DataFrame] = []
    for d in list_available_days(csv_dir):
        if d < start or d > end:
            continue
        ticks = load_day(d, csv_dir=csv_dir, symbol=symbol, use_cache=use_cache)
        frames.append(ticks.df)

    if not frames:
        empty = pl.DataFrame(schema=Ticks.REQUIRED_COLS)
        return Ticks(df=empty, symbol=symbol)

    return Ticks(df=pl.concat(frames, how="vertical").sort("ts_ny"), symbol=symbol)
