"""Shared types used across detectors and the PD Array selector.

Pure data containers — frozen dataclasses + enums. No I/O, no globals.
Detector modules in `structure/`, `signals/imbalance/`, `signals/blocks/`,
`signals/liquidity/`, `signals/ranges/` all consume and emit these types.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Literal


class Direction(StrEnum):
    BULL = "BULL"
    BEAR = "BEAR"


class Side(StrEnum):
    BSL = "BSL"
    SSL = "SSL"


class PDArrayKind(StrEnum):
    STRUCTURAL_EXTREME = "structural_extreme"
    BREAKER = "breaker"
    MITIGATION = "mitigation"
    OPENING_GAP = "opening_gap"
    FVG = "fvg"
    ORDER_BLOCK = "order_block"
    REJECTION = "rejection"


PD_RANK: dict[PDArrayKind, int] = {
    PDArrayKind.STRUCTURAL_EXTREME: 1,
    PDArrayKind.BREAKER: 2,
    PDArrayKind.MITIGATION: 3,
    PDArrayKind.OPENING_GAP: 4,
    PDArrayKind.FVG: 5,
    PDArrayKind.ORDER_BLOCK: 6,
    PDArrayKind.REJECTION: 7,
}


@dataclass(frozen=True, slots=True)
class Interval:
    """Closed price interval [low, high]."""

    low: float
    high: float

    def __post_init__(self) -> None:
        if self.low > self.high:
            raise ValueError(f"Interval requires low <= high: got {self.low}, {self.high}")

    @property
    def mid(self) -> float:
        return (self.low + self.high) / 2.0

    @property
    def width(self) -> float:
        return self.high - self.low

    def contains(self, price: float) -> bool:
        return self.low <= price <= self.high

    def intersects(self, other: Interval) -> bool:
        return not (self.high < other.low or other.high < self.low)

    def intersection(self, other: Interval) -> Interval | None:
        if not self.intersects(other):
            return None
        return Interval(max(self.low, other.low), min(self.high, other.high))


SwingKind = Literal["HIGH", "LOW"]


@dataclass(frozen=True, slots=True)
class Swing:
    """A confirmed swing point on a specific timeframe."""

    index: int
    ts_ny: datetime
    kind: SwingKind
    price: float
    confirmed_at_index: int


@dataclass(frozen=True, slots=True)
class Leg:
    """A maximal contiguous displacement leg."""

    direction: Direction
    start_index: int
    end_index: int
    range: Interval

    @property
    def length(self) -> int:
        return self.end_index - self.start_index + 1


StructureEventKind = Literal["BoS", "ChoCH", "MSS"]


@dataclass(frozen=True, slots=True)
class StructureEvent:
    kind: StructureEventKind
    direction: Direction
    index: int
    ts_ny: datetime
    broken_price: float


@dataclass(frozen=True, slots=True)
class FVG:
    """Fair Value Gap (BISI or SIBI)."""

    direction: Direction
    anchor_index: int           # index of the first bar of the 3-bar pattern
    ts_ny: datetime             # ts of the middle (displacement) bar
    range: Interval
    invalidated_at: int | None = None

    @property
    def ce(self) -> float:
        return self.range.mid


@dataclass(frozen=True, slots=True)
class BPR:
    range: Interval
    bisi: FVG
    sibi: FVG


@dataclass(frozen=True, slots=True)
class VolumeImbalance:
    direction: Direction
    anchor_index: int
    range: Interval


@dataclass(frozen=True, slots=True)
class OrderBlock:
    direction: Direction
    anchor_index: int
    range: Interval
    leg_ref: Leg
    fvg_ref: FVG | None = None
    htf_anchored: bool = False
    touch_count: int = 0
    invalidated_at: int | None = None

    @property
    def mt(self) -> float:
        return self.range.mid


@dataclass(frozen=True, slots=True)
class Breaker:
    direction: Direction
    range: Interval
    origin_ob: OrderBlock
    sweep_index: int
    invalidator_index: int


@dataclass(frozen=True, slots=True)
class Mitigation:
    direction: Direction
    range: Interval
    origin_ob: OrderBlock
    touch_index: int


@dataclass(frozen=True, slots=True)
class Rejection:
    direction: Direction
    anchor_index: int
    range: Interval
    sweep_pool_price: float


@dataclass(frozen=True, slots=True)
class LiquidityPool:
    side: Side
    price: float
    anchor_swings: tuple[Swing, ...]
    created_at_index: int
    is_cluster: bool = False
    tf: str = "1m"
    swept_count: int = 0
    invalidated_at: int | None = None


@dataclass(frozen=True, slots=True)
class Sweep:
    side: Side
    index: int
    ts_ny: datetime
    pool: LiquidityPool
    depth: float


@dataclass(frozen=True, slots=True)
class Inducement:
    """A sweep classified as inducement (minor-TF sweep during prevailing trend)."""

    sweep: Sweep
    bias_direction: Direction


@dataclass(frozen=True, slots=True)
class DealingRange:
    """Active dealing range on a reference timeframe."""

    range: Interval
    last_high_swing: Swing
    last_low_swing: Swing

    @property
    def equilibrium(self) -> float:
        return self.range.mid


@dataclass(frozen=True, slots=True)
class OTEZone:
    direction: Direction
    leg_range: Interval
    zone: Interval
    sweet_spot: float


@dataclass(frozen=True, slots=True)
class PDArrayRef:
    """Generic reference to an active PD Array, used by the selector."""

    kind: PDArrayKind
    side: Literal["PREMIUM", "DISCOUNT"]
    range: Interval
    created_at_index: int
    obj: object = field(repr=False)  # back-reference to the concrete object
    htf_anchored: bool = True

    @property
    def rank(self) -> int:
        return PD_RANK[self.kind]
