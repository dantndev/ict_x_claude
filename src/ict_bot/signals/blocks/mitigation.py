"""Mitigation Block detection (concept 07).

A Mitigation Block is an OB that the market revisits *without* a prior
opposite-side sweep — continuation structure. If a sweep precedes the touch,
the path is a Breaker (concept 06), NOT a Mitigation.
"""

from __future__ import annotations

from dataclasses import dataclass

from ict_bot.data.models import Bars
from ict_bot.signals.base import Direction, Mitigation, OrderBlock, Side, Sweep


@dataclass(frozen=True, slots=True)
class MitigationConfig:
    retest_grace_bars: int = 3
    only_fresh_obs: bool = True
    require_no_intervening_sweep: bool = True


def detect_mitigations(
    bars: Bars,
    obs: list[OrderBlock],
    sweeps: list[Sweep],
    *,
    config: MitigationConfig | None = None,
) -> list[Mitigation]:
    """Find first retest of each OB that respects the OB without a prior opposite sweep."""
    cfg = config or MitigationConfig()
    if bars.empty:
        return []
    highs = bars.df.get_column("high").to_list()
    lows = bars.df.get_column("low").to_list()
    out: list[Mitigation] = []
    for ob in obs:
        if cfg.only_fresh_obs and ob.touch_count > 0:
            continue
        # Find first retest
        first_touch = None
        for t in range(ob.anchor_index + 1, len(highs)):
            touched = (
                (ob.direction == Direction.BULL and lows[t] <= ob.range.high)
                or (ob.direction == Direction.BEAR and highs[t] >= ob.range.low)
            )
            if touched:
                first_touch = t
                break
        if first_touch is None:
            continue
        # No intervening sweep against OB direction
        against = Side.SSL if ob.direction == Direction.BULL else Side.BSL
        if cfg.require_no_intervening_sweep:
            had_sweep = any(
                s.side == against and ob.anchor_index < s.index < first_touch
                for s in sweeps
            )
            if had_sweep:
                continue
        # Within grace window, OB should not be invalidated
        if ob.invalidated_at is not None \
                and ob.invalidated_at <= first_touch + cfg.retest_grace_bars:
            continue
        out.append(
            Mitigation(
                direction=ob.direction,
                range=ob.range,
                origin_ob=ob,
                touch_index=first_touch,
            ),
        )
    return out
