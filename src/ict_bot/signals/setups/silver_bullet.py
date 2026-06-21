"""Silver Bullet setup — time-anchored at 10:00-11:00 NY (AM) or 14:00-15:00 NY (PM).

Composes any FVG-based entry inside the Silver Bullet window. Mechanically
identical to `mss_fvg` / Unicorn but gated by the time tag.
"""

from __future__ import annotations

from dataclasses import dataclass

from ict_bot.data.models import Bars
from ict_bot.sessions.killzones import (
    SessionsConfig,
    silver_bullet_am,
    silver_bullet_pm,
)
from ict_bot.signals.base import (
    FVG,
    Direction,
    LiquidityPool,
    Side,
)
from ict_bot.signals.setups.base import Signal, TradeSide


@dataclass(frozen=True, slots=True)
class SilverBulletConfig:
    sl_offset_ticks: int = 8
    tick_size: float = 0.25
    min_rr: float = 1.5
    fallback_tp_r: float = 3.0
    min_tp_distance_in_risks: float = 1.0
    tp_strategy: str = "nearest_pool"    # "nearest_pool" | "fixed_R"
    fixed_tp_r: float = 2.0


def detect_silver_bullet(
    bars: Bars,
    fvgs: list[FVG],
    pools: list[LiquidityPool],
    *,
    config: SilverBulletConfig | None = None,
    sessions_config: SessionsConfig | None = None,
) -> list[Signal]:
    cfg = config or SilverBulletConfig()
    s_cfg = sessions_config or SessionsConfig()
    if bars.empty or not fvgs:
        return []
    ts_ny = bars.df.get_column("ts_ny").to_list()
    lows = bars.df.get_column("low").to_list()
    highs = bars.df.get_column("high").to_list()
    out: list[Signal] = []
    for g in fvgs:
        ts = g.ts_ny
        in_window = silver_bullet_am(ts, s_cfg) or silver_bullet_pm(ts, s_cfg)
        if not in_window:
            continue
        entry = g.range.high if g.direction == Direction.BULL else g.range.low
        offset = cfg.sl_offset_ticks * cfg.tick_size
        mid = g.anchor_index + 1
        if mid >= len(lows):
            continue
        sl = lows[mid] - offset if g.direction == Direction.BULL else highs[mid] + offset
        risk = abs(entry - sl)
        if risk <= 0:
            continue
        if cfg.tp_strategy == "fixed_R":
            tp = (entry + cfg.fixed_tp_r * risk
                  if g.direction == Direction.BULL
                  else entry - cfg.fixed_tp_r * risk)
        else:
            min_tp_dist = cfg.min_tp_distance_in_risks * risk
            if g.direction == Direction.BULL:
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
            tp = (
                tp_pool.price
                if tp_pool is not None
                else (entry + cfg.fallback_tp_r * risk
                      if g.direction == Direction.BULL
                      else entry - cfg.fallback_tp_r * risk)
            )
        if abs(tp - entry) / risk < cfg.min_rr:
            continue
        out.append(
            Signal(
                setup_name="silver_bullet",
                side=TradeSide.BUY if g.direction == Direction.BULL else TradeSide.SELL,
                direction=g.direction,
                entry_price=entry,
                stop_loss=sl,
                take_profit=tp,
                ts_ny=ts_ny[g.anchor_index],
                bar_index=g.anchor_index,
                components=(g,),
                confidence=1.5,
                notes="silver_bullet_am" if silver_bullet_am(ts, s_cfg) else "silver_bullet_pm",
            ),
        )
    return out
