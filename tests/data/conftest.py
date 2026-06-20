"""Fixtures for data-layer tests: synthetic Bars and Ticks."""

from __future__ import annotations

from datetime import datetime, timedelta

import polars as pl
import pytest

from ict_bot.data.models import Bars, Ticks
from ict_bot.utils.tz import NY


def _make_1m_bars(start: datetime, n: int, *, symbol: str = "TEST") -> Bars:
    rows = []
    price = 100.0
    for i in range(n):
        rows.append(
            {
                "ts_ny": (start + timedelta(minutes=i)),
                "open": price,
                "high": price + 1.0,
                "low": price - 1.0,
                "close": price + 0.5,
                "volume": 10 + i,
            }
        )
        price += 0.5
    df = pl.DataFrame(rows).with_columns(
        pl.col("ts_ny").dt.replace_time_zone(NY.key)
    )
    return Bars(df=df, tf="1m", symbol=symbol)


@pytest.fixture()
def bars_1m_60() -> Bars:
    """60 contiguous 1-minute bars starting 2026-03-22 18:00 NY."""
    start = datetime(2026, 3, 22, 18, 0)
    return _make_1m_bars(start, 60)


@pytest.fixture()
def bars_1m_with_gap() -> Bars:
    """1m bars with a 10-minute gap inserted at index 30."""
    start = datetime(2026, 3, 22, 18, 0)
    bars = _make_1m_bars(start, 60).df
    keep_mask = (pl.arange(0, bars.height) < 30) | (pl.arange(0, bars.height) >= 40)
    bars = bars.filter(keep_mask)
    return Bars(df=bars, tf="1m", symbol="TEST")


@pytest.fixture()
def ticks_sample() -> Ticks:
    """A tiny Ticks DataFrame matching the L2 schema's required columns."""
    rows = []
    base = datetime(2026, 6, 9, 9, 27, 47, 500_000)
    for i in range(20):
        rows.append({
            "ts_ny": base + timedelta(milliseconds=100 * i),
            "ts_utc": base + timedelta(milliseconds=100 * i, hours=4),
            "symbol": "TEST",
            "best_bid": 29711.0 + 0.25 * (i % 3),
            "best_ask": 29711.5 + 0.25 * (i % 3),
            "spread_pts": 0.5,
            "obi_top10": 0.05 * (i - 10),
            "fp_delta": -1 if i % 2 else 1,
        })
    df = pl.DataFrame(rows).with_columns(
        pl.col("ts_ny").dt.replace_time_zone(NY.key),
        pl.col("ts_utc").dt.replace_time_zone("UTC"),
    )
    return Ticks(df=df, symbol="TEST")
