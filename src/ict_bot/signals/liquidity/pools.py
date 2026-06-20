"""Liquidity pool construction from swing points (concept 10 §3.1, §3.2)."""

from __future__ import annotations

from dataclasses import dataclass

from ict_bot.signals.base import LiquidityPool, Side, Swing


@dataclass(frozen=True, slots=True)
class PoolConfig:
    tolerance_ticks: int = 2
    tick_size: float = 0.25     # NQ default
    min_cluster_size: int = 2


def pools_from_swings(swings: list[Swing], *, tf: str = "1m") -> list[LiquidityPool]:
    """Single-swing pools: every swing high → BSL, every swing low → SSL."""
    out: list[LiquidityPool] = []
    for s in swings:
        side = Side.BSL if s.kind == "HIGH" else Side.SSL
        out.append(
            LiquidityPool(
                side=side,
                price=s.price,
                anchor_swings=(s,),
                created_at_index=s.confirmed_at_index,
                is_cluster=False,
                tf=tf,
            ),
        )
    return out


def cluster_equal_extremes(
    swings: list[Swing],
    *,
    config: PoolConfig | None = None,
    tf: str = "1m",
) -> list[LiquidityPool]:
    """Collapse runs of same-kind swings within a price tolerance into cluster pools.

    Cluster price = max for BSL (highs), min for SSL (lows) — the actual stop trigger.
    """
    cfg = config or PoolConfig()
    tol = cfg.tolerance_ticks * cfg.tick_size
    out: list[LiquidityPool] = []
    for kind, side in (("HIGH", Side.BSL), ("LOW", Side.SSL)):
        same = [s for s in swings if s.kind == kind]
        same.sort(key=lambda s: s.price)
        i = 0
        while i < len(same):
            j = i
            while j + 1 < len(same) and abs(same[j + 1].price - same[i].price) <= tol:
                j += 1
            cluster = same[i : j + 1]
            if len(cluster) >= cfg.min_cluster_size:
                trigger_price = (
                    max(s.price for s in cluster) if side == Side.BSL
                    else min(s.price for s in cluster)
                )
                created = max(s.confirmed_at_index for s in cluster)
                out.append(
                    LiquidityPool(
                        side=side,
                        price=trigger_price,
                        anchor_swings=tuple(cluster),
                        created_at_index=created,
                        is_cluster=True,
                        tf=tf,
                    ),
                )
            i = j + 1
    return out
