"""Tests for the timezone helpers."""

from __future__ import annotations

from datetime import datetime, time

from ict_bot.utils.tz import NY, UTC, is_between, midnight_ny, ny_date, ny_time, to_ny, to_utc


def test_to_ny_localizes_naive_as_utc():
    dt = datetime(2026, 6, 20, 12, 0)  # naive
    ny = to_ny(dt)
    assert ny.tzinfo == NY
    assert ny.hour == 8  # 12:00 UTC == 08:00 NY (EDT in summer)


def test_to_utc_converts_back():
    dt = datetime(2026, 6, 20, 8, 0, tzinfo=NY)
    utc = to_utc(dt)
    assert utc.tzinfo == UTC
    assert utc.hour == 12


def test_ny_time_and_date():
    dt = datetime(2026, 6, 20, 8, 30, tzinfo=NY)
    assert ny_time(dt) == time(8, 30)
    assert ny_date(dt) == dt.date()


def test_is_between_inside_inclusive():
    assert is_between(time(8, 30), time(8, 0), time(9, 0)) is True
    assert is_between(time(9, 0), time(8, 0), time(9, 0)) is True


def test_is_between_outside():
    assert is_between(time(7, 0), time(8, 0), time(9, 0)) is False


def test_is_between_wrap_around():
    # 23:30 inside [20:00, 02:00] (Asia session window)
    assert is_between(time(23, 30), time(20, 0), time(2, 0)) is True
    # 03:00 NOT inside [20:00, 02:00]
    assert is_between(time(3, 0), time(20, 0), time(2, 0)) is False


def test_midnight_ny():
    dt = midnight_ny(datetime(2026, 6, 20).date())
    assert dt.tzinfo == NY
    assert dt.hour == 0
    assert dt.minute == 0
