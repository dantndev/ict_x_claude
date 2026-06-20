"""Parquet cache helpers for OHLCV and L2 data."""

from __future__ import annotations

from pathlib import Path

import polars as pl

from ict_bot.utils.logging import get_logger

log = get_logger(__name__)


def cache_dir(root: Path) -> Path:
    """Return (creating if needed) the parquet cache directory."""
    p = root / "data" / "cache"
    p.mkdir(parents=True, exist_ok=True)
    return p


def write_parquet(df: pl.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(path, compression="zstd", compression_level=3)
    log.debug("parquet_written", path=str(path), rows=df.height)


def read_parquet(path: Path) -> pl.DataFrame | None:
    if not path.exists():
        return None
    df = pl.read_parquet(path)
    log.debug("parquet_read", path=str(path), rows=df.height)
    return df


def ohlcv_cache_path(root: Path, symbol: str, tf: str) -> Path:
    return cache_dir(root) / f"ohlcv_{tf}_{symbol}.parquet"


def l2_cache_path(root: Path, symbol: str, day: str) -> Path:
    """day = 'YYYY-MM-DD'"""
    return cache_dir(root) / "l2" / symbol / f"{day}.parquet"
