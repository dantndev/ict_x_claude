"""MSS + FVG setup — enter on retest of the FVG produced by the MSS leg."""

from __future__ import annotations

from dataclasses import dataclass

from ict_bot.data.models import Bars
from ict_bot.signals.base import (
    FVG,
    Direction,
    LiquidityPool,
    Side,
    StructureEvent,
)
from ict_bot.signals.setups.base import Signal, TradeSide


@dataclass(frozen=True, slots=True)
class MssFvgConfig:
    sl_offset_ticks: int = 8
    tick_size: float = 0.25
    min_rr: float = 1.5
    fallback_tp_r: float = 3.0
    fvg_lookback_bars: int = 8
    min_tp_distance_in_risks: float = 1.0
    tp_strategy: str = "nearest_pool"    # "nearest_pool" | "fixed_R"
    fixed_tp_r: float = 2.0


def detect_mss_fvg(  # noqa: PLR0912
    bars: Bars,
    mss_events: list[StructureEvent],
    fvgs: list[FVG],
    pools: list[LiquidityPool],
    *,
    config: MssFvgConfig | None = None,
) -> list[Signal]:
    """Pair each MSS event with the nearest preceding FVG (matching direction)."""
    cfg = config or MssFvgConfig()
    if bars.empty or not mss_events or not fvgs:
        return []
    ts_ny = bars.df.get_column("ts_ny").to_list()
    out: list[Signal] = []
    for ev in mss_events:
        if ev.kind != "MSS":
            continue
        # Find an FVG of matching direction anchored within lookback
        candidates = [
            g for g in fvgs
            if g.direction == ev.direction
            and ev.index - cfg.fvg_lookback_bars <= g.anchor_index <= ev.index
        ]
        if not candidates:
            continue
        # pick the FVG with anchor closest to MSS index (latest)
        g = max(candidates, key=lambda x: x.anchor_index)
        # Entry at FVG's proximal edge
        entry = g.range.high if ev.direction == Direction.BULL else g.range.low
        # SL behind FVG's bar extreme
        lows = bars.df.get_column("low").to_list()
        highs = bars.df.get_column("high").to_list()
        mid = g.anchor_index + 1
        offset = cfg.sl_offset_ticks * cfg.tick_size
        sl = lows[mid] - offset if ev.direction == Direction.BULL else highs[mid] + offset
        risk = abs(entry - sl)
        if risk <= 0:
            continue
        if cfg.tp_strategy == "fixed_R":
            tp_pool = None
        else:
            min_tp_dist = cfg.min_tp_distance_in_risks * risk
            if ev.direction == Direction.BULL:
                tp_pool = min(
                    (p for p in pools if p.side == Side.BSL
                     and (p.price - entry) >= min_tp_dist),
                    key=lambda p: p.price - entry,
                    default=None,
                )
            else:
                tp_pool = min(
                    (p for p in pools if p.side == Side.SSL
                     and (entry - p.price) >= min_tp_dist),
                    key=lambda p: entry - p.price,
                    default=None,
                )
        if cfg.tp_strategy == "fixed_R":
            tp = (entry + cfg.fixed_tp_r * risk
                  if ev.direction == Direction.BULL
                  else entry - cfg.fixed_tp_r * risk)
        elif tp_pool is not None:
            tp = tp_pool.price
        else:
            tp = (entry + cfg.fallback_tp_r * risk
                  if ev.direction == Direction.BULL
                  else entry - cfg.fallback_tp_r * risk)
        if abs(tp - entry) / risk < cfg.min_rr:
            continue
        out.append(
            Signal(
                setup_name="mss_fvg",
                side=TradeSide.BUY if ev.direction == Direction.BULL else TradeSide.SELL,
                direction=ev.direction,
                entry_price=entry,
                stop_loss=sl,
                take_profit=tp,
                ts_ny=ts_ny[ev.index],
                bar_index=ev.index,
                components=(ev, g),
                confidence=1.0,
            ),
        )
    return out
