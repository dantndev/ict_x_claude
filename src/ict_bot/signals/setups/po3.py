"""Power of Three (PO3) session-level state machine (concept 12).

Walks through a session window classifying its phase (accumulation /
manipulation / distribution) using the prevailing HTF bias, sweeps registry,
and MSS events. Emits an "entry-allowed" gate that other setups (Unicorn,
MSS+FVG, OB+OTE) can use as additional confluence.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ict_bot.data.models import Bars
from ict_bot.signals.base import (
    Direction,
    Side,
    StructureEvent,
    Sweep,
)


class PO3Phase(StrEnum):
    ACCUMULATION = "ACCUMULATION"
    MANIPULATION = "MANIPULATION"
    DISTRIBUTION = "DISTRIBUTION"
    DISABLED = "DISABLED"


@dataclass(frozen=True, slots=True)
class PO3Config:
    judas_window_bars: int = 90
    max_accum_bars: int = 60


@dataclass(frozen=True, slots=True)
class PO3Snapshot:
    bias: Direction | None
    phase: PO3Phase
    judas_index: int | None
    distribution_start_index: int | None


def evaluate_po3(
    bars: Bars,
    session_start_index: int,
    session_end_index: int,
    bias_direction: Direction | None,
    sweeps: list[Sweep],
    mss_events: list[StructureEvent],
    *,
    config: PO3Config | None = None,
) -> PO3Snapshot:
    """Compute the PO3 phase as of `session_end_index` for the session.

    `bias_direction=None` (range HTF state) → PO3 is DISABLED.
    """
    cfg = config or PO3Config()
    if bias_direction is None:
        return PO3Snapshot(bias=None, phase=PO3Phase.DISABLED,
                           judas_index=None, distribution_start_index=None)
    _ = bars  # signature documentation; bars used for future extension

    against_side = Side.SSL if bias_direction == Direction.BULL else Side.BSL
    # First sweep against bias within the judas window
    judas = None
    for s in sweeps:
        if s.side != against_side:
            continue
        if session_start_index <= s.index <= session_end_index \
                and s.index <= session_start_index + cfg.judas_window_bars:
            judas = s
            break

    # MSS in bias direction after judas
    dist_start = None
    for ev in mss_events:
        if ev.kind != "MSS":
            continue
        if ev.direction != bias_direction:
            continue
        if judas is not None and ev.index > judas.index and ev.index <= session_end_index:
            dist_start = ev.index
            break
        if judas is None and ev.index <= session_end_index \
                and ev.index >= session_start_index:
            dist_start = ev.index
            break

    if dist_start is not None:
        phase = PO3Phase.DISTRIBUTION
    elif judas is not None:
        phase = PO3Phase.MANIPULATION
    else:
        phase = PO3Phase.ACCUMULATION

    return PO3Snapshot(
        bias=bias_direction,
        phase=phase,
        judas_index=judas.index if judas is not None else None,
        distribution_start_index=dist_start,
    )


def po3_entry_allowed(
    snapshot: PO3Snapshot,
    price: float,
    direction: Direction,
    mid_open: float | None,
) -> bool:
    """Gate function for setups operating during a session under PO3 supervision."""
    if snapshot.phase != PO3Phase.DISTRIBUTION:
        return False
    if direction != snapshot.bias:
        return False
    if mid_open is None:
        return True
    if direction == Direction.BULL and price >= mid_open:
        return False
    return not (direction == Direction.BEAR and price <= mid_open)


__all__ = [
    "PO3Config",
    "PO3Phase",
    "PO3Snapshot",
    "evaluate_po3",
    "po3_entry_allowed",
]
