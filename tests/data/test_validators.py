"""Tests for gap / duplicate / timezone validators."""

from __future__ import annotations

import polars as pl

from ict_bot.data.models import Bars, Ticks
from ict_bot.data.validators import (
    check_bar_duplicates,
    check_bar_gaps,
    check_bar_timezone,
    check_tick_monotonicity,
)
from ict_bot.utils.tz import NY


def test_gaps_none_on_contiguous(bars_1m_60: Bars):
    report = check_bar_gaps(bars_1m_60)
    assert report.gaps == []
    assert report.total_missing == 0


def test_gaps_detected(bars_1m_with_gap: Bars):
    report = check_bar_gaps(bars_1m_with_gap)
    assert len(report.gaps) == 1
    _, _, missing = report.gaps[0]
    assert missing == 10


def test_duplicates_none(bars_1m_60: Bars):
    rep = check_bar_duplicates(bars_1m_60)
    assert rep.count == 0


def test_duplicates_detected(bars_1m_60: Bars):
    dup_df = pl.concat([bars_1m_60.df, bars_1m_60.df.head(1)])
    dup = Bars(df=dup_df, tf="1m", symbol="TEST")
    rep = check_bar_duplicates(dup)
    assert rep.count == 1


def test_timezone_ok(bars_1m_60: Bars):
    rep = check_bar_timezone(bars_1m_60)
    assert rep.ok is True
    assert rep.tz_name == NY.key


def test_tick_monotonicity_ok(ticks_sample: Ticks):
    assert check_tick_monotonicity(ticks_sample) is True
