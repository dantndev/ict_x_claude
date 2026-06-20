"""PD Array selector (concept 09).

Aggregates every typed PD Array (FVG, OB, Breaker, Mitigation, Rejection) into
a single ranked registry and answers price-level queries with the dominant
array at any given moment.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

from ict_bot.signals.base import (
    BPR,
    FVG,
    PD_RANK,
    Breaker,
    Direction,
    Mitigation,
    OrderBlock,
    PDArrayKind,
    PDArrayRef,
    Rejection,
)


def _to_ref(obj: object) -> PDArrayRef:
    """Wrap a typed PD object in a PDArrayRef."""
    if isinstance(obj, OrderBlock):
        side: Literal["PREMIUM", "DISCOUNT"] = (
            "DISCOUNT" if obj.direction == Direction.BULL else "PREMIUM"
        )
        return PDArrayRef(
            kind=PDArrayKind.ORDER_BLOCK,
            side=side,
            range=obj.range,
            created_at_index=obj.anchor_index,
            obj=obj,
            htf_anchored=obj.htf_anchored,
        )
    if isinstance(obj, Breaker):
        side = "DISCOUNT" if obj.direction == Direction.BULL else "PREMIUM"
        return PDArrayRef(
            kind=PDArrayKind.BREAKER,
            side=side,
            range=obj.range,
            created_at_index=obj.invalidator_index,
            obj=obj,
            htf_anchored=True,
        )
    if isinstance(obj, Mitigation):
        side = "DISCOUNT" if obj.direction == Direction.BULL else "PREMIUM"
        return PDArrayRef(
            kind=PDArrayKind.MITIGATION,
            side=side,
            range=obj.range,
            created_at_index=obj.touch_index,
            obj=obj,
            htf_anchored=True,
        )
    if isinstance(obj, FVG):
        side = "DISCOUNT" if obj.direction == Direction.BULL else "PREMIUM"
        return PDArrayRef(
            kind=PDArrayKind.FVG,
            side=side,
            range=obj.range,
            created_at_index=obj.anchor_index,
            obj=obj,
            htf_anchored=True,
        )
    if isinstance(obj, BPR):
        # Treat a BPR as an FVG-rank object for selector purposes (the doc places it
        # between rank 4 and 5; v1 = rank 5 like a regular FVG).
        return PDArrayRef(
            kind=PDArrayKind.FVG,
            side="DISCOUNT",  # BPRs are direction-agnostic; selector treats as discount-ish
            range=obj.range,
            created_at_index=obj.bisi.anchor_index,
            obj=obj,
            htf_anchored=True,
        )
    if isinstance(obj, Rejection):
        side = "DISCOUNT" if obj.direction == Direction.BULL else "PREMIUM"
        return PDArrayRef(
            kind=PDArrayKind.REJECTION,
            side=side,
            range=obj.range,
            created_at_index=obj.anchor_index,
            obj=obj,
            htf_anchored=True,
        )
    raise TypeError(f"Unknown PD array object: {type(obj).__name__}")


def build_registry(items: Iterable[object]) -> list[PDArrayRef]:
    return [_to_ref(x) for x in items]


def pd_arrays_at(
    price: float,
    direction: Literal["BUY", "SELL"],
    registry: list[PDArrayRef],
    *,
    require_htf_anchor: bool = True,
) -> list[PDArrayRef]:
    """Return all eligible PD arrays at `price` for `direction`, ordered by rank."""
    side = "DISCOUNT" if direction == "BUY" else "PREMIUM"
    out = [
        r for r in registry
        if r.range.contains(price) and r.side == side
        and (not require_htf_anchor or r.htf_anchored)
    ]
    out.sort(key=lambda r: (PD_RANK[r.kind], -r.created_at_index))
    return out


def dominant_pd_array_at(
    price: float, direction: Literal["BUY", "SELL"], registry: list[PDArrayRef],
    *, require_htf_anchor: bool = True,
) -> PDArrayRef | None:
    cands = pd_arrays_at(price, direction, registry, require_htf_anchor=require_htf_anchor)
    return cands[0] if cands else None
