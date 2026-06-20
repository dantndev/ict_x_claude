"""Breaker Block detection (concept 06).

A Breaker is born from an OB that was invalidated, when a prior opposite-side
liquidity sweep (concept 10) occurred between the OB's anchor and its
invalidation. The Breaker's direction is OPPOSITE the original OB.
"""

from __future__ import annotations

from dataclasses import dataclass

from ict_bot.signals.base import Breaker, Direction, OrderBlock, Side, Sweep


@dataclass(frozen=True, slots=True)
class BreakerConfig:
    require_prior_sweep: bool = True


def detect_breakers(
    obs: list[OrderBlock], sweeps: list[Sweep], *, config: BreakerConfig | None = None,
) -> list[Breaker]:
    """Promote invalidated OBs that had a preceding opposite-side sweep into Breakers."""
    cfg = config or BreakerConfig()
    out: list[Breaker] = []
    for ob in obs:
        if ob.invalidated_at is None:
            continue
        required_side = Side.SSL if ob.direction == Direction.BULL else Side.BSL
        prior = None
        for s in sweeps:
            if s.side != required_side:
                continue
            # keep the latest (closest to invalidation) — per concept doc decision
            if ob.anchor_index < s.index < ob.invalidated_at \
                    and (prior is None or s.index > prior.index):
                prior = s
        if cfg.require_prior_sweep and prior is None:
            continue
        out.append(
            Breaker(
                direction=Direction.BEAR if ob.direction == Direction.BULL else Direction.BULL,
                range=ob.range,
                origin_ob=ob,
                sweep_index=prior.index if prior is not None else -1,
                invalidator_index=ob.invalidated_at,
            ),
        )
    return out
