"""CME OHLCV CSV loader (Databento format) — multi-year, multi-contract.

Source format (one row per minute per contract):
    ts_event,rtype,publisher_id,instrument_id,open,high,low,close,volume,symbol
    2021-03-25T00:00:00.000000000Z,33,1,9485,12805.25,12820.75,...,NQM1

Cleaning steps:
    1. Filter to a single futures family ("NQ" or "MNQ").
    2. Drop calendar-spread rows (symbols containing "-").
    3. Pick the dominant front-month per trading day = symbol with the highest
       daily volume. Concatenate to form a continuous series with implicit rolls.
    4. Convert ts_event (UTC, ns precision) → ts_ny (America/New_York).
    5. Deduplicate (ts_ny, symbol), sort ascending.

Output: `Bars(tf="1m")` ready for the rest of the pipeline.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl

from ict_bot.config.settings import REPO_ROOT
from ict_bot.data.cache import cache_dir, read_parquet, write_parquet
from ict_bot.data.models import Bars
from ict_bot.utils.logging import get_logger
from ict_bot.utils.tz import NY

log = get_logger(__name__)


def _cache_path(repo_root: Path, family: str) -> Path:
    return cache_dir(repo_root) / f"cme_{family}_continuous_1m.parquet"


def load_cme_csv(
    csv_path: Path | str,
    *,
    family: str = "MNQ",
    start: date | None = None,
    end: date | None = None,
    use_cache: bool = True,
    refresh: bool = False,
    repo_root: Path = REPO_ROOT,
) -> Bars:
    """Load and clean a Databento-format CME CSV into a continuous front-month Bars.

    Args:
        csv_path: Path to the raw CSV.
        family: Futures family prefix to keep ("NQ" or "MNQ").
        start/end: Optional date filters (NY calendar).
        use_cache/refresh: Cache the cleaned series as parquet.
        repo_root: Root for the cache directory.
    """
    csv_path = Path(csv_path)
    cache_path = _cache_path(repo_root, family)

    if use_cache and not refresh:
        cached = read_parquet(cache_path)
        if cached is not None:
            log.info("cme_cache_hit", path=str(cache_path), rows=cached.height,
                     family=family)
            df = cached
            if start is not None:
                df = df.filter(pl.col("ts_ny").dt.date() >= start)
            if end is not None:
                df = df.filter(pl.col("ts_ny").dt.date() <= end)
            return Bars(df=df, tf="1m", symbol=family)

    if not csv_path.exists():
        raise FileNotFoundError(f"CME CSV not found: {csv_path}")

    log.info("cme_csv_load_start", path=str(csv_path), family=family)

    # Stream-parse with lazy operations; collect filtered result
    lf = (
        pl.scan_csv(csv_path, infer_schema_length=10_000)
        # Keep only the requested family, drop calendar spreads
        .filter(
            pl.col("symbol").str.starts_with(family)
            & ~pl.col("symbol").str.contains("-"),
        )
        # Ensure we keep only the exact family (NQ-prefix would also match MNQ);
        # contract codes are 4-5 chars: NQ + month-letter + year-digit(s)
        .filter(
            pl.col("symbol").str.len_chars().is_between(
                len(family) + 2, len(family) + 3,
            ),
        )
    )

    raw = lf.collect()
    log.info("cme_csv_filtered", rows=raw.height, family=family)

    # Parse ts_event (UTC, ns) → ts_ny (NY)
    raw = raw.with_columns(
        pl.col("ts_event")
        .str.to_datetime(format="%Y-%m-%dT%H:%M:%S%.fZ", time_unit="us", strict=False)
        .dt.replace_time_zone("UTC")
        .dt.convert_time_zone(NY.key)
        .alias("ts_ny"),
    ).drop_nulls("ts_ny")

    # Pick dominant front-month per NY calendar day = max(daily_volume) symbol
    raw = raw.with_columns(pl.col("ts_ny").dt.date().alias("ny_date"))
    daily_vol = (
        raw.group_by(["ny_date", "symbol"])
        .agg(pl.col("volume").sum().alias("daily_volume"))
    )
    front_month_per_day = (
        daily_vol.sort(["ny_date", "daily_volume"], descending=[False, True])
        .group_by("ny_date", maintain_order=True)
        .agg(pl.col("symbol").first().alias("front_month_symbol"))
    )
    log.info("cme_front_month_picked", days=front_month_per_day.height)

    # Join + filter to keep only rows of the front-month for that day
    joined = raw.join(front_month_per_day, on="ny_date", how="inner").filter(
        pl.col("symbol") == pl.col("front_month_symbol"),
    )

    canonical = (
        joined.select(
            "ts_ny",
            pl.col("open").cast(pl.Float64),
            pl.col("high").cast(pl.Float64),
            pl.col("low").cast(pl.Float64),
            pl.col("close").cast(pl.Float64),
            pl.col("volume").cast(pl.Int64),
            pl.col("symbol").alias("contract_symbol"),
        )
        .unique(subset=["ts_ny"], keep="first")
        .sort("ts_ny")
    )

    log.info("cme_cleaned", rows=canonical.height)
    write_parquet(canonical, cache_path)

    df_out = canonical
    if start is not None:
        df_out = df_out.filter(pl.col("ts_ny").dt.date() >= start)
    if end is not None:
        df_out = df_out.filter(pl.col("ts_ny").dt.date() <= end)
    return Bars(df=df_out, tf="1m", symbol=family)
