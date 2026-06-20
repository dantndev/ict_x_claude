"""Tests for the 1m → higher-TF resampler."""

from __future__ import annotations

import pytest

from ict_bot.data.models import Bars
from ict_bot.data.resampler import resample


def test_resample_identity(bars_1m_60: Bars):
    out = resample(bars_1m_60, "1m")
    assert out is bars_1m_60


def test_resample_to_5m_groups_60_into_12(bars_1m_60: Bars):
    out = resample(bars_1m_60, "5m")
    assert len(out) == 12
    # OHLC invariants
    src = bars_1m_60.df
    out_df = out.df
    for i, group_start in enumerate(range(0, 60, 5)):
        chunk = src.slice(group_start, 5)
        row = out_df.row(i, named=True)
        assert row["open"] == chunk["open"][0]
        assert row["high"] == chunk["high"].max()
        assert row["low"] == chunk["low"].min()
        assert row["close"] == chunk["close"][-1]
        assert row["volume"] == chunk["volume"].sum()


def test_resample_to_15m_groups_60_into_4(bars_1m_60: Bars):
    out = resample(bars_1m_60, "15m")
    assert len(out) == 4


def test_resample_to_1h_groups_60_into_1(bars_1m_60: Bars):
    out = resample(bars_1m_60, "1H")
    assert len(out) == 1
    row = out.df.row(0, named=True)
    assert row["open"] == bars_1m_60.df["open"][0]
    assert row["close"] == bars_1m_60.df["close"][-1]
    assert row["volume"] == bars_1m_60.df["volume"].sum()


def test_resample_rejects_finer_target(bars_1m_60: Bars):
    five = resample(bars_1m_60, "5m")
    with pytest.raises(ValueError, match="finer"):
        resample(five, "1m")
