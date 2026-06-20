"""Data layer: loaders, validators, resampler, and domain models.

Public API:
    Bars, Ticks, Timeframe       — domain models
    fetch_ohlcv_1m               — HTTP loader for the backtest API
    load_day, load_range,
    list_available_days          — L2 CSV loaders
    resample                     — 1m → higher timeframe
    check_bar_gaps,
    check_bar_duplicates,
    check_bar_timezone           — validators
"""

from ict_bot.data.loaders.l2_csv import (
    list_available_days,
    load_day,
    load_range,
)
from ict_bot.data.loaders.ohlcv_http import fetch_ohlcv_1m
from ict_bot.data.models import Bars, Ticks, Timeframe
from ict_bot.data.resampler import resample
from ict_bot.data.validators import (
    check_bar_duplicates,
    check_bar_gaps,
    check_bar_timezone,
    check_tick_monotonicity,
)

__all__ = [
    "Bars",
    "Ticks",
    "Timeframe",
    "check_bar_duplicates",
    "check_bar_gaps",
    "check_bar_timezone",
    "check_tick_monotonicity",
    "fetch_ohlcv_1m",
    "list_available_days",
    "load_day",
    "load_range",
    "resample",
]
