"""Balanced Price Range — overlap of opposing FVGs (concept 04 §1.3)."""

from __future__ import annotations

from ict_bot.signals.base import BPR, FVG, Direction


def detect_bprs(fvgs: list[FVG]) -> list[BPR]:
    """Return all BPRs from a list of FVGs.

    A BPR is the intersection of a BISI and a SIBI whose ranges overlap in
    price. Either time order is acceptable.
    """
    bulls = [g for g in fvgs if g.direction == Direction.BULL and g.invalidated_at is None]
    bears = [g for g in fvgs if g.direction == Direction.BEAR and g.invalidated_at is None]
    out: list[BPR] = []
    for b in bulls:
        for s in bears:
            inter = b.range.intersection(s.range)
            if inter is None:
                continue
            out.append(BPR(range=inter, bisi=b, sibi=s))
    return out
