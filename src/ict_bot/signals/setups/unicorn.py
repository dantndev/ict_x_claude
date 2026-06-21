"""Unicorn Model setup — Breaker ∩ FVG, optionally inside OTE (concept 14)."""

from __future__ import annotations

from dataclasses import dataclass

from ict_bot.data.models import Bars
from ict_bot.signals.base import (
    FVG,
    Breaker,
    Direction,
    LiquidityPool,
    Side,
)
from ict_bot.signals.ranges.ote import ote_zone
from ict_bot.signals.setups.base import Signal, TradeSide


@dataclass(frozen=True, slots=True)
class UnicornConfig:
    require_inside_ote: bool = False
    sl_offset_ticks: int = 8
    tick_size: float = 0.25
    min_rr: float = 1.5
    fallback_tp_r: float = 3.0
    same_leg_window_factor: float = 1.5     # window = leg.length * factor
    tp_strategy: str = "nearest_pool"       # "nearest_pool" | "fixed_R"
    fixed_tp_r: float = 2.0


def _proximal_edge(intersection_low: float, intersection_high: float,
                   direction: Direction) -> float:
    """Long enters at the upper edge (top of zone); short at the lower edge."""
    return intersection_high if direction == Direction.BULL else intersection_low


def _fvg_anchor_extreme(bars: Bars, fvg: FVG, direction: Direction) -> float:
    """Return the low (bull) or high (bear) of the FVG's middle (displacement) bar."""
    lows = bars.df.get_column("low").to_list()
    highs = bars.df.get_column("high").to_list()
    mid = fvg.anchor_index + 1
    if mid >= len(lows):
        mid = fvg.anchor_index
    return float(lows[mid]) if direction == Direction.BULL else float(highs[mid])


def _nearest_opposite_pool(pools: list[LiquidityPool], price: float,
                           direction: Direction) -> LiquidityPool | None:
    if direction == Direction.BULL:
        cands = [p for p in pools if p.side == Side.BSL and p.price > price]
        return min(cands, key=lambda p: p.price - price, default=None)
    cands = [p for p in pools if p.side == Side.SSL and p.price < price]
    return min(cands, key=lambda p: price - p.price, default=None)


def detect_unicorns(
    bars: Bars,
    breakers: list[Breaker],
    fvgs: list[FVG],
    pools: list[LiquidityPool],
    *,
    config: UnicornConfig | None = None,
) -> list[Signal]:
    """Return Unicorn-Model signals.

    Each signal carries: entry at the intersection's proximal edge,
    SL behind the FVG-anchor bar extreme (± `sl_offset_ticks`), TP at the
    nearest opposite-side pool or a fallback `fallback_tp_r * risk`.
    Setup is rejected if RR < `min_rr` or if the same-leg constraint fails.
    """
    cfg = config or UnicornConfig()
    if bars.empty or not breakers or not fvgs:
        return []
    ts_ny = bars.df.get_column("ts_ny").to_list()
    out: list[Signal] = []
    for b in breakers:
        # Unicorn pairs the Breaker with an FVG of the SAME direction as the
        # trade (= Breaker.direction), anchored during the leg that BROKE the
        # origin OB (between sweep_index and invalidator_index). This is the
        # "breaking leg" per concept 14 — distinct from the OB's origin leg.
        same_dir_fvgs = [g for g in fvgs if g.direction == b.direction]
        breaking_lo = max(0, b.sweep_index)
        breaking_hi = b.invalidator_index
        # OTE zone is computed on the ORIGIN leg's price range as the reference.
        z_origin = ote_zone(b.origin_ob.leg_ref).zone
        for g in same_dir_fvgs:
            if not (breaking_lo <= g.anchor_index <= breaking_hi):
                continue
            inter = b.range.intersection(g.range)
            if inter is None:
                continue
            inside_ote = inter.intersects(z_origin)
            if cfg.require_inside_ote and not inside_ote:
                continue

            entry = _proximal_edge(inter.low, inter.high, b.direction)
            sl_anchor = _fvg_anchor_extreme(bars, g, b.direction)
            offset = cfg.sl_offset_ticks * cfg.tick_size
            sl = sl_anchor - offset if b.direction == Direction.BULL else sl_anchor + offset
            risk = abs(entry - sl)
            if risk <= 0:
                continue
            if cfg.tp_strategy == "fixed_R":
                tp = (entry + cfg.fixed_tp_r * risk
                      if b.direction == Direction.BULL
                      else entry - cfg.fixed_tp_r * risk)
            else:
                tp_pool = _nearest_opposite_pool(pools, entry, b.direction)
                if tp_pool is not None:
                    tp = tp_pool.price
                else:
                    tp = (entry + cfg.fallback_tp_r * risk
                          if b.direction == Direction.BULL
                          else entry - cfg.fallback_tp_r * risk)
            reward = abs(tp - entry)
            if reward / risk < cfg.min_rr:
                continue
            sig_ts = ts_ny[b.invalidator_index] if b.invalidator_index < len(ts_ny) \
                else ts_ny[-1]
            out.append(
                Signal(
                    setup_name="unicorn",
                    side=TradeSide.BUY if b.direction == Direction.BULL else TradeSide.SELL,
                    direction=b.direction,
                    entry_price=entry,
                    stop_loss=sl,
                    take_profit=tp,
                    ts_ny=sig_ts,
                    bar_index=b.invalidator_index,
                    components=(b, g),
                    confidence=1.0 + (0.5 if inside_ote else 0.0),
                    notes="inside_ote" if inside_ote else "",
                ),
            )
    return out
