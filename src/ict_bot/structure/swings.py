"""Swing High / Swing Low detection (concept 01).

Implements the strict N-bar fractal: bar `t` is a swing high iff its high is
strictly greater than the highs of N bars on each side. Symmetric for swing
lows. Confirmation requires N future bars.
"""

from __future__ import annotations

import polars as pl

from ict_bot.data.models import Bars
from ict_bot.signals.base import Swing


def detect_swings(bars: Bars, *, n: int = 1) -> list[Swing]:
    """Return all confirmed swing points in `bars`.

    Args:
        bars: OHLCV bars (any timeframe).
        n: Fractal half-width (n=1 → 3-bar fractal). Must be >= 1.

    Confirmation lag: a swing at index `t` is confirmed after bar `t + n` closes.
    Provisional (unconfirmed) swings are NOT emitted; backtests cannot peek.
    """
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n}")
    if bars.empty:
        return []

    highs = bars.df.get_column("high").to_list()
    lows = bars.df.get_column("low").to_list()
    ts_ny = bars.df.get_column("ts_ny").to_list()
    m = len(highs)

    swings: list[Swing] = []
    for t in range(n, m - n):
        h_t = highs[t]
        is_sh = all(h_t > highs[t - k] and h_t > highs[t + k] for k in range(1, n + 1))
        if is_sh:
            swings.append(
                Swing(
                    index=t,
                    ts_ny=ts_ny[t],
                    kind="HIGH",
                    price=h_t,
                    confirmed_at_index=t + n,
                ),
            )

        l_t = lows[t]
        is_sl = all(l_t < lows[t - k] and l_t < lows[t + k] for k in range(1, n + 1))
        if is_sl:
            swings.append(
                Swing(
                    index=t,
                    ts_ny=ts_ny[t],
                    kind="LOW",
                    price=l_t,
                    confirmed_at_index=t + n,
                ),
            )

    return swings


def swings_to_df(swings: list[Swing]) -> pl.DataFrame:
    """Return a Polars DataFrame view of the swing list (for inspection / plotting)."""
    if not swings:
        return pl.DataFrame(
            schema={
                "index": pl.Int64,
                "ts_ny": pl.Datetime,
                "kind": pl.Utf8,
                "price": pl.Float64,
                "confirmed_at_index": pl.Int64,
            },
        )
    return pl.DataFrame(
        {
            "index": [s.index for s in swings],
            "ts_ny": [s.ts_ny for s in swings],
            "kind": [s.kind for s in swings],
            "price": [s.price for s in swings],
            "confirmed_at_index": [s.confirmed_at_index for s in swings],
        },
    )
