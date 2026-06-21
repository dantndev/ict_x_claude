"""Hard safety mechanism — when tripped, every subsequent order is rejected
and the engine flattens existing positions on its next opportunity.

Reasons that trip the switch automatically:
- Daily loss limit breached (delegated check; raises here).
- Number of consecutive losses exceeded the configured cap.
- Manual `trip()` call from operator.

A tripped kill switch can only be reset by an explicit human action
(`reset()`), never by time alone.
"""

from __future__ import annotations

from dataclasses import dataclass


class KillSwitchTripped(Exception):
    """Raised when an order is submitted while the kill switch is tripped."""


@dataclass(slots=True)
class KillSwitch:
    tripped: bool = False
    reason: str = ""

    def trip(self, reason: str) -> None:
        if not self.tripped:
            self.tripped = True
            self.reason = reason

    def reset(self) -> None:
        self.tripped = False
        self.reason = ""

    def assert_armed(self) -> None:
        if self.tripped:
            raise KillSwitchTripped(self.reason)
