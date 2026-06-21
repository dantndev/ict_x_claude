"""OB + OTE setup — emit a Signal at the bar where price retests the OB.

The OB is detected at its anchor, but the actionable signal happens later when
price returns to the OB's body (the retest). We scan forward from each OB's
anchor for the first retest bar; if no body-close-beyond-MT invalidation has
fired before that retest, the setup is live and a Signal is emitted at the
retest bar.
"""

from __future__ import annotations

from dataclasses import dataclass

from ict_bot.data.models import Bars
from ict_bot.signals.base import (
    Direction,
    LiquidityPool,
    OrderBlock,
    Side,
)
from ict_bot.signals.ranges.ote import ote_zone
from ict_bot.signals.setups.base import Signal, TradeSide


@dataclass(frozen=True, slots=True)
class ObOteConfig:
    sl_offset_ticks: int = 8
    tick_size: float = 0.25
    min_rr: float = 1.5
    fallback_tp_r: float = 3.0
    require_inside_ote: bool = False     # OTE is a CONFLUENCE boost, not a gate
    min_tp_distance_in_risks: float = 1.0  # tp_pool must be >= 1R away to count


def _first_retest_index(bars: Bars, ob: OrderBlock) -> int | None:
    highs = bars.df.get_column("high").to_list()
    lows = bars.df.get_column("low").to_list()
    upper_bound = ob.invalidated_at if ob.invalidated_at is not None else len(highs)
    for t in range(ob.anchor_index + 1, upper_bound):
        if ob.direction == Direction.BULL and lows[t] <= ob.range.high:
            return t
        if ob.direction == Direction.BEAR and highs[t] >= ob.range.low:
            return t
    return None


def detect_ob_ote(
    bars: Bars,
    obs: list[OrderBlock],
    pools: list[LiquidityPool],
    *,
    config: ObOteConfig | None = None,
) -> list[Signal]:
    cfg = config or ObOteConfig()
    if bars.empty or not obs:
        return []
    ts_ny = bars.df.get_column("ts_ny").to_list()
    out: list[Signal] = []
    for ob in obs:
        retest_t = _first_retest_index(bars, ob)
        if retest_t is None:
            continue
        z = ote_zone(ob.leg_ref).zone
        inside_ote = ob.range.intersects(z)
        if cfg.require_inside_ote and not inside_ote:
            continue
        entry = ob.range.high if ob.direction == Direction.BULL else ob.range.low
        offset = cfg.sl_offset_ticks * cfg.tick_size
        sl = (ob.range.low - offset
              if ob.direction == Direction.BULL
              else ob.range.high + offset)
        risk = abs(entry - sl)
        if risk <= 0:
            continue
        min_tp_dist = cfg.min_tp_distance_in_risks * risk
        if ob.direction == Direction.BULL:
            tp_pool = min(
                (p for p in pools if p.side == Side.BSL and (p.price - entry) >= min_tp_dist),
                key=lambda p: p.price - entry,
                default=None,
            )
        else:
            tp_pool = min(
                (p for p in pools if p.side == Side.SSL and (entry - p.price) >= min_tp_dist),
                key=lambda p: entry - p.price,
                default=None,
            )
        tp = (
            tp_pool.price
            if tp_pool is not None
            else (entry + cfg.fallback_tp_r * risk
                  if ob.direction == Direction.BULL
                  else entry - cfg.fallback_tp_r * risk)
        )
        if abs(tp - entry) / risk < cfg.min_rr:
            continue
        out.append(
            Signal(
                setup_name="ob_ote",
                side=TradeSide.BUY if ob.direction == Direction.BULL else TradeSide.SELL,
                direction=ob.direction,
                entry_price=entry,
                stop_loss=sl,
                take_profit=tp,
                ts_ny=ts_ny[retest_t],
                bar_index=retest_t,
                components=(ob,),
                confidence=1.0 + (0.5 if inside_ote else 0.0),
                notes="inside_ote" if inside_ote else "",
            ),
        )
    return out
