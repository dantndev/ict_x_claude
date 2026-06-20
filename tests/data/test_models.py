"""Tests for the Bars / Ticks domain models."""

from __future__ import annotations

from datetime import datetime

import polars as pl
import pytest

from ict_bot.data.models import Bars, Ticks


def test_bars_rejects_missing_columns():
    df = pl.DataFrame({"ts_ny": [], "open": []})
    with pytest.raises(ValueError, match="missing required columns"):
        Bars(df=df, tf="1m", symbol="TEST")


def test_bars_rejects_unknown_tf(bars_1m_60: Bars):
    with pytest.raises(ValueError, match="Unknown timeframe"):
        Bars(df=bars_1m_60.df, tf="2m", symbol="TEST")  # type: ignore[arg-type]


def test_bars_first_last_ts(bars_1m_60: Bars):
    first = bars_1m_60.first_ts()
    last = bars_1m_60.last_ts()
    assert isinstance(first, datetime)
    assert isinstance(last, datetime)
    assert last > first
    assert len(bars_1m_60) == 60


def test_bars_slice_inclusive(bars_1m_60: Bars):
    first = bars_1m_60.first_ts()
    assert first is not None
    sliced = bars_1m_60.slice(start=first, end=first)
    assert len(sliced) == 1


def test_ticks_rejects_missing_columns():
    df = pl.DataFrame({"ts_ny": []})
    with pytest.raises(ValueError, match="missing required columns"):
        Ticks(df=df, symbol="TEST")


def test_ticks_round_trip(ticks_sample: Ticks):
    assert len(ticks_sample) == 20
    assert "obi_top10" in ticks_sample.df.columns
