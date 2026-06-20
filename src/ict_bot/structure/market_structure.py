"""Market Structure: HH/HL/LH/LL state, BoS, ChoCH, MSS (concept 02).

Walks confirmed swings to maintain a (BULL/BEAR/RANGE) state, then for each
bar's close emits structure events. MSS additionally requires displacement +
FVG on the breaking leg + a prior opposite-side sweep — the trigger.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ict_bot.data.models import Bars
from ict_bot.signals.base import (
    FVG,
    Direction,
    Side,
    StructureEvent,
    Swing,
)
from ict_bot.signals.liquidity.sweep import PoolConsumption

State = Literal["BULL", "BEAR", "RANGE"]


@dataclass(frozen=True, slots=True)
class MarketStructureConfig:
    bos_require_body_close: bool = True


@dataclass
class _Last:
    HH: Swing | None = None
    HL: Swing | None = None
    LH: Swing | None = None
    LL: Swing | None = None


def _classify_swing(s: Swing, prior_same_kind: Swing | None) -> str:
    """Return role: HH / HL / LH / LL (or NEW if no prior)."""
    if prior_same_kind is None:
        return "HH" if s.kind == "HIGH" else "HL" if s.kind == "LOW" else "?"
    if s.kind == "HIGH":
        return "HH" if s.price > prior_same_kind.price else "LH"
    return "HL" if s.price > prior_same_kind.price else "LL"


def _update_state(last: _Last) -> State:
    """Latest two swing-roles determine the state."""
    if last.HH is not None and last.HL is not None:
        last_high_idx = last.HH.confirmed_at_index
        last_low_idx = last.HL.confirmed_at_index
        last_lh_idx = last.LH.confirmed_at_index if last.LH else -1
        last_ll_idx = last.LL.confirmed_at_index if last.LL else -1
        if max(last_high_idx, last_low_idx) > max(last_lh_idx, last_ll_idx):
            return "BULL"
    if last.LH is not None and last.LL is not None:
        last_lh_idx = last.LH.confirmed_at_index
        last_ll_idx = last.LL.confirmed_at_index
        last_hh_idx = last.HH.confirmed_at_index if last.HH else -1
        last_hl_idx = last.HL.confirmed_at_index if last.HL else -1
        if max(last_lh_idx, last_ll_idx) > max(last_hh_idx, last_hl_idx):
            return "BEAR"
    return "RANGE"


def detect_structure_events(  # noqa: PLR0912, PLR0915
    bars: Bars,
    swings: list[Swing],
    *,
    displacement_per_bar: list[Direction | None] | None = None,
    fvgs: list[FVG] | None = None,
    consumptions: list[PoolConsumption] | None = None,
    config: MarketStructureConfig | None = None,
) -> list[StructureEvent]:
    """Walk bars+swings chronologically and emit BoS / ChoCH / MSS events.

    The full MSS gate (displacement + FVG + prior sweep) requires all three
    optional inputs. If any are None, MSS is downgraded to ChoCH.
    """
    _ = config  # reserved for future tuning
    if bars.empty:
        return []
    closes = bars.df.get_column("close").to_list()
    ts_ny = bars.df.get_column("ts_ny").to_list()
    m = len(closes)

    swings_by_confirm = sorted(swings, key=lambda s: s.confirmed_at_index)
    last = _Last()
    state: State = "RANGE"
    swing_ptr = 0
    events: list[StructureEvent] = []

    sweeps_by_index: dict[int, Side] = {}
    if consumptions is not None:
        # Treat pool consumptions (not sweeps) as the trigger for MSS prior-sweep
        # check — they signify the opposite pool was *taken*, opening the door
        # for a structure flip on the next break.
        for c in consumptions:
            sweeps_by_index[c.index] = c.side

    fvgs_by_anchor: dict[int, list[FVG]] = {}
    if fvgs is not None:
        for g in fvgs:
            fvgs_by_anchor.setdefault(g.anchor_index, []).append(g)

    def _had_recent_consumption(side: Side, t: int, lookback: int = 50) -> bool:
        return any(
            sweeps_by_index.get(s) == side
            for s in range(max(0, t - lookback), t)
        )

    def _has_breaking_fvg(direction: Direction, t: int, lookback: int = 10) -> bool:
        for s in range(max(0, t - lookback), t + 1):
            for g in fvgs_by_anchor.get(s, []):
                if g.direction == direction:
                    return True
        return False

    for t in range(m):
        # Promote any swings whose confirmed_at_index ≤ t
        while swing_ptr < len(swings_by_confirm) and \
                swings_by_confirm[swing_ptr].confirmed_at_index <= t:
            s = swings_by_confirm[swing_ptr]
            if s.kind == "HIGH":
                role = _classify_swing(s, last.HH or last.LH)
                if role == "HH":
                    last.HH = s
                else:
                    last.LH = s
            else:
                role = _classify_swing(s, last.HL or last.LL)
                if role == "HL":
                    last.HL = s
                else:
                    last.LL = s
            state = _update_state(last)
            swing_ptr += 1

        # Continuation BoS
        if state == "BULL" and last.HH is not None and closes[t] > last.HH.price:
            events.append(
                StructureEvent(kind="BoS", direction=Direction.BULL, index=t,
                               ts_ny=ts_ny[t], broken_price=last.HH.price),
            )
        if state == "BEAR" and last.LL is not None and closes[t] < last.LL.price:
            events.append(
                StructureEvent(kind="BoS", direction=Direction.BEAR, index=t,
                               ts_ny=ts_ny[t], broken_price=last.LL.price),
            )

        # Reversal candidates: ChoCH (or MSS if gates satisfied)
        if state == "BEAR" and last.LH is not None and closes[t] > last.LH.price:
            disp_ok = displacement_per_bar is not None \
                and displacement_per_bar[t] == Direction.BULL
            fvg_ok = _has_breaking_fvg(Direction.BULL, t)
            sweep_ok = _had_recent_consumption(Side.SSL, t)
            if disp_ok and fvg_ok and sweep_ok:
                events.append(
                    StructureEvent(kind="MSS", direction=Direction.BULL, index=t,
                                   ts_ny=ts_ny[t], broken_price=last.LH.price),
                )
                state = "BULL"
            else:
                events.append(
                    StructureEvent(kind="ChoCH", direction=Direction.BULL, index=t,
                                   ts_ny=ts_ny[t], broken_price=last.LH.price),
                )

        if state == "BULL" and last.HL is not None and closes[t] < last.HL.price:
            disp_ok = displacement_per_bar is not None \
                and displacement_per_bar[t] == Direction.BEAR
            fvg_ok = _has_breaking_fvg(Direction.BEAR, t)
            sweep_ok = _had_recent_consumption(Side.BSL, t)
            if disp_ok and fvg_ok and sweep_ok:
                events.append(
                    StructureEvent(kind="MSS", direction=Direction.BEAR, index=t,
                                   ts_ny=ts_ny[t], broken_price=last.HL.price),
                )
                state = "BEAR"
            else:
                events.append(
                    StructureEvent(kind="ChoCH", direction=Direction.BEAR, index=t,
                                   ts_ny=ts_ny[t], broken_price=last.HL.price),
                )

    return events
