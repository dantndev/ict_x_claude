"""Inducement: a sweep classified as a minor-TF stop hunt during prevailing trend
(concept 10 §3.4)."""

from __future__ import annotations

from ict_bot.signals.base import Direction, Inducement, Sweep


def classify_inducements(
    sweeps: list[Sweep],
    *,
    minor_tf: str = "1m",
    prevailing_direction: Direction,
) -> list[Inducement]:
    """Mark sweeps on `minor_tf` pools as Inducements when prevailing trend is unchanged.

    A more sophisticated version (per concept 10 §3.4) would query the trend
    state at each sweep's bar; v1 receives a constant prevailing direction.
    """
    out: list[Inducement] = []
    for s in sweeps:
        if s.pool.tf != minor_tf:
            continue
        out.append(Inducement(sweep=s, bias_direction=prevailing_direction))
    return out
