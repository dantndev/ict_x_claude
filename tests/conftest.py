"""Shared pytest fixtures across the test tree.

`make_bars_fn` is used by structure, signals, and (later) backtest tests to
synthesize Bars from a sequence of (open, high, low, close) tuples without
having to wire the full Polars schema by hand.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta

import polars as pl
import pytest

from ict_bot.data.models import Bars
from ict_bot.utils.tz import NY


def _make_bars(
    ohlc: Sequence[tuple[float, float, float, float]],
    *,
    start: datetime | None = None,
    tf_minutes: int = 1,
) -> Bars:
    base = start or datetime(2026, 6, 1, 9, 0)
    rows = []
    for i, (o, h, low, c) in enumerate(ohlc):
        rows.append(
            {
                "ts_ny": base + timedelta(minutes=i * tf_minutes),
                "open": float(o),
                "high": float(h),
                "low": float(low),
                "close": float(c),
                "volume": 10 + i,
            },
        )
    df = pl.DataFrame(rows).with_columns(pl.col("ts_ny").dt.replace_time_zone(NY.key))
    return Bars(df=df, tf="1m", symbol="TEST")


@pytest.fixture()
def make_bars_fn():
    return _make_bars
