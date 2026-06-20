"""Setup composers: Unicorn, MSS+FVG, OB+OTE, Silver Bullet, PO3."""

from ict_bot.signals.setups.base import Signal, TradeSide
from ict_bot.signals.setups.mss_fvg import MssFvgConfig, detect_mss_fvg
from ict_bot.signals.setups.ob_ote import ObOteConfig, detect_ob_ote
from ict_bot.signals.setups.po3 import (
    PO3Config,
    PO3Phase,
    PO3Snapshot,
    evaluate_po3,
    po3_entry_allowed,
)
from ict_bot.signals.setups.silver_bullet import SilverBulletConfig, detect_silver_bullet
from ict_bot.signals.setups.unicorn import UnicornConfig, detect_unicorns

__all__ = [
    "MssFvgConfig",
    "ObOteConfig",
    "PO3Config",
    "PO3Phase",
    "PO3Snapshot",
    "Signal",
    "SilverBulletConfig",
    "TradeSide",
    "UnicornConfig",
    "detect_mss_fvg",
    "detect_ob_ote",
    "detect_silver_bullet",
    "detect_unicorns",
    "evaluate_po3",
    "po3_entry_allowed",
]
