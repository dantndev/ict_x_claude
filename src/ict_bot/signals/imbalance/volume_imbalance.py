"""Volume Imbalance — body-to-body gap between two consecutive candles (concept 04 §1.4)."""

from __future__ import annotations

from ict_bot.data.models import Bars
from ict_bot.signals.base import Direction, Interval, VolumeImbalance


def detect_volume_imbalances(bars: Bars) -> list[VolumeImbalance]:
    """Return all bullish/bearish volume imbalances in `bars`."""
    if bars.empty:
        return []
    opens = bars.df.get_column("open").to_list()
    closes = bars.df.get_column("close").to_list()
    m = len(opens)
    out: list[VolumeImbalance] = []
    for t in range(m - 1):
        c_t = closes[t]
        o_t = opens[t]
        o_next = opens[t + 1]
        body_top_t = max(o_t, c_t)
        body_bot_t = min(o_t, c_t)
        # Bullish: next candle opens above close of t AND close equals body top of t
        if o_next > c_t and c_t == body_top_t:
            out.append(
                VolumeImbalance(
                    direction=Direction.BULL,
                    anchor_index=t,
                    range=Interval(low=c_t, high=o_next),
                ),
            )
        # Bearish: next opens below close of t AND close equals body bottom of t
        if o_next < c_t and c_t == body_bot_t:
            out.append(
                VolumeImbalance(
                    direction=Direction.BEAR,
                    anchor_index=t,
                    range=Interval(low=o_next, high=c_t),
                ),
            )
    return out
