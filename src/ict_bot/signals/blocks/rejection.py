"""Rejection Block detection (concept 08).

A wick beyond a liquidity pool with the body closing back inside the prior bar's
range, where the wick is at least `wick_to_body_min` times the body. One-bar
(same-bar reversal) and two-bar (next-bar body confirmation) variants are
both supported.
"""

from __future__ import annotations

from dataclasses import dataclass

from ict_bot.data.models import Bars
from ict_bot.signals.base import Direction, Interval, LiquidityPool, Rejection, Side


@dataclass(frozen=True, slots=True)
class RejectionConfig:
    wick_to_body_min: float = 2.0
    lookforward_bars: int = 1


def detect_rejections(  # noqa: PLR0912
    bars: Bars,
    pools: list[LiquidityPool],
    *,
    config: RejectionConfig | None = None,
) -> list[Rejection]:
    """Scan bars for wick rejections at any active pool."""
    cfg = config or RejectionConfig()
    if bars.empty or not pools:
        return []
    opens = bars.df.get_column("open").to_list()
    highs = bars.df.get_column("high").to_list()
    lows = bars.df.get_column("low").to_list()
    closes = bars.df.get_column("close").to_list()
    m = len(opens)
    out: list[Rejection] = []
    for p in pools:
        for t in range(p.created_at_index, m):
            if p.side == Side.SSL:
                wick_pierces = lows[t] < p.price and min(opens[t], closes[t]) >= p.price
                if not wick_pierces:
                    continue
                for k in range(cfg.lookforward_bars + 1):
                    if t + k >= m:
                        break
                    body = abs(closes[t + k] - opens[t + k])
                    lower_wick = min(opens[t + k], closes[t + k]) - lows[t + k]
                    if body <= 0:
                        continue
                    if lower_wick / body < cfg.wick_to_body_min:
                        continue
                    if t == 0 or closes[t + k] >= lows[t - 1]:
                        out.append(
                            Rejection(
                                direction=Direction.BULL,
                                anchor_index=t,
                                range=Interval(
                                    low=lows[t],
                                    high=min(opens[t], closes[t]),
                                ),
                                sweep_pool_price=p.price,
                            ),
                        )
                        break
            else:  # BSL
                wick_pierces = highs[t] > p.price and max(opens[t], closes[t]) <= p.price
                if not wick_pierces:
                    continue
                for k in range(cfg.lookforward_bars + 1):
                    if t + k >= m:
                        break
                    body = abs(closes[t + k] - opens[t + k])
                    upper_wick = highs[t + k] - max(opens[t + k], closes[t + k])
                    if body <= 0:
                        continue
                    if upper_wick / body < cfg.wick_to_body_min:
                        continue
                    if t == 0 or closes[t + k] <= highs[t - 1]:
                        out.append(
                            Rejection(
                                direction=Direction.BEAR,
                                anchor_index=t,
                                range=Interval(
                                    low=max(opens[t], closes[t]),
                                    high=highs[t],
                                ),
                                sweep_pool_price=p.price,
                            ),
                        )
                        break
    return out
