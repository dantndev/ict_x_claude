"""Dealing Range + Premium/Discount classification (concept 11)."""

from __future__ import annotations

from typing import Literal

from ict_bot.signals.base import DealingRange, Interval, Swing


def dealing_range_at(swings: list[Swing], at_index: int) -> DealingRange | None:
    """Most recent confirmed SH and SL at or before `at_index` bracket the range."""
    last_high: Swing | None = None
    last_low: Swing | None = None
    for s in swings:
        if s.confirmed_at_index > at_index:
            continue
        if s.kind == "HIGH" and (
            last_high is None or s.confirmed_at_index > last_high.confirmed_at_index
        ):
            last_high = s
        if s.kind == "LOW" and (
            last_low is None or s.confirmed_at_index > last_low.confirmed_at_index
        ):
            last_low = s
    if last_high is None or last_low is None:
        return None
    lo = min(last_low.price, last_high.price)
    hi = max(last_low.price, last_high.price)
    return DealingRange(
        range=Interval(low=lo, high=hi),
        last_high_swing=last_high,
        last_low_swing=last_low,
    )


def classify_price(price: float, dr: DealingRange) -> Literal["PREMIUM", "DISCOUNT", "EQUILIBRIUM"]:
    eq = dr.equilibrium
    if price > eq:
        return "PREMIUM"
    if price < eq:
        return "DISCOUNT"
    return "EQUILIBRIUM"
