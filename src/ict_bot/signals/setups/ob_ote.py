"""OB + OTE setup — Order Block located inside the OTE zone of the active leg."""

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
        if ob.invalidated_at is not None:
            continue
        z = ote_zone(ob.leg_ref).zone
        if not ob.range.intersects(z):
            continue
        entry = ob.range.high if ob.direction == Direction.BULL else ob.range.low
        offset = cfg.sl_offset_ticks * cfg.tick_size
        sl = (ob.range.low - offset
              if ob.direction == Direction.BULL
              else ob.range.high + offset)
        if ob.direction == Direction.BULL:
            tp_pool = min(
                (p for p in pools if p.side == Side.BSL and p.price > entry),
                key=lambda p: p.price - entry,
                default=None,
            )
        else:
            tp_pool = min(
                (p for p in pools if p.side == Side.SSL and p.price < entry),
                key=lambda p: entry - p.price,
                default=None,
            )
        risk = abs(entry - sl)
        if risk <= 0:
            continue
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
                ts_ny=ts_ny[ob.anchor_index],
                bar_index=ob.anchor_index,
                components=(ob,),
                confidence=1.0,
            ),
        )
    return out
