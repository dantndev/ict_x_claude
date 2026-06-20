"""Integration tests against the real localhost API and the real L2 CSV directory.

These are gated by the `integration` marker. Run with:
    pytest -m integration

They will be skipped automatically when the resources are not reachable.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from ict_bot.config.settings import get_settings
from ict_bot.data.loaders.l2_csv import list_available_days, load_day
from ict_bot.data.loaders.ohlcv_http import fetch_ohlcv_1m
from ict_bot.data.resampler import resample
from ict_bot.data.validators import check_bar_timezone

pytestmark = pytest.mark.integration


def _api_alive(url: str) -> bool:
    try:
        with httpx.Client(timeout=3.0) as c:
            r = c.head(url)
        return r.status_code < 500
    except Exception:
        return False


def _l2_dir_exists() -> bool:
    return get_settings().ict_l2_csv_dir.exists()


@pytest.mark.skipif(
    not _api_alive(get_settings().ict_backtest_api_url),
    reason="localhost backtest API not reachable",
)
def test_fetch_ohlcv_and_resample(tmp_path: Path):
    bars = fetch_ohlcv_1m(repo_root=tmp_path, use_cache=False)
    assert len(bars) > 0
    assert bars.tf == "1m"

    tz = check_bar_timezone(bars)
    assert tz.ok, f"timezone report: {tz}"

    # Resample to 15m and 1H; lengths must shrink monotonically.
    b15 = resample(bars, "15m")
    b1h = resample(bars, "1H")
    assert len(b15) < len(bars)
    assert len(b1h) < len(b15)


@pytest.mark.skipif(
    not _l2_dir_exists(),
    reason="L2 CSV dir not present",
)
def test_load_one_l2_day(tmp_path: Path):
    days = list_available_days()
    if not days:
        pytest.skip("no L2 days available")
    ticks = load_day(days[-1], repo_root=tmp_path, use_cache=False)
    assert len(ticks) > 0
    assert "obi_top10" in ticks.df.columns
