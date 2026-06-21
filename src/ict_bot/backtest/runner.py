"""End-to-end backtest pipeline: bars → detectors → setup → engine → metrics.

This orchestrates the full Phase-3/4/5 flow on a single bar series for a
single setup. The CLI (`cli.py`) is a thin wrapper around `run_pipeline`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ict_bot.backtest.engine import BacktestConfig, BacktestResult, run_backtest
from ict_bot.data.models import Bars
from ict_bot.signals.blocks.breaker import detect_breakers
from ict_bot.signals.blocks.order_block import (
    detect_order_blocks,
    invalidate_order_blocks,
)
from ict_bot.signals.imbalance.fvg import FVGConfig, detect_fvgs, invalidate_fvgs
from ict_bot.signals.liquidity.pools import pools_from_swings
from ict_bot.signals.liquidity.sweep import detect_sweeps_and_consumptions
from ict_bot.signals.setups.base import Signal
from ict_bot.signals.setups.mss_fvg import MssFvgConfig, detect_mss_fvg
from ict_bot.signals.setups.ob_ote import ObOteConfig, detect_ob_ote
from ict_bot.signals.setups.silver_bullet import SilverBulletConfig, detect_silver_bullet
from ict_bot.signals.setups.unicorn import UnicornConfig, detect_unicorns
from ict_bot.structure.displacement import (
    DisplacementConfig,
    aggregate_legs,
    detect_displacement,
)
from ict_bot.structure.market_structure import detect_structure_events
from ict_bot.structure.swings import detect_swings
from ict_bot.utils.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class PipelineConfig:
    swing_n: int = 1
    displacement: DisplacementConfig = field(default_factory=DisplacementConfig)
    fvg: FVGConfig = field(
        default_factory=lambda: FVGConfig(
            require_displacement=True, min_gap_ticks=1, tick_size=0.25,
        ),
    )
    unicorn: UnicornConfig = field(default_factory=UnicornConfig)
    mss_fvg: MssFvgConfig = field(default_factory=MssFvgConfig)
    ob_ote: ObOteConfig = field(default_factory=ObOteConfig)
    silver_bullet: SilverBulletConfig = field(default_factory=SilverBulletConfig)
    setups: tuple[str, ...] = ("unicorn", "mss_fvg", "ob_ote", "silver_bullet")


def detect_all_signals(bars: Bars, *, cfg: PipelineConfig | None = None) -> list[Signal]:
    """Run the full detector + setup pipeline; return all candidate signals."""
    cfg = cfg or PipelineConfig()
    swings = detect_swings(bars, n=cfg.swing_n)
    log.info("swings_detected", count=len(swings))
    per_bar = detect_displacement(bars, config=cfg.displacement)
    legs = aggregate_legs(bars, per_bar)
    log.info("legs_detected", count=len(legs))
    fvgs = invalidate_fvgs(bars, detect_fvgs(bars, config=cfg.fvg, displacement=per_bar))
    log.info("fvgs_detected", count=len(fvgs))
    pools = pools_from_swings(swings, tf=bars.tf)
    sweeps, consumptions = detect_sweeps_and_consumptions(bars, pools)
    log.info("sweeps_detected", count=len(sweeps), consumptions=len(consumptions))
    mss_events = detect_structure_events(
        bars, swings, displacement_per_bar=per_bar, fvgs=fvgs, consumptions=consumptions,
    )
    log.info("structure_events", count=len(mss_events))
    obs = invalidate_order_blocks(bars, detect_order_blocks(bars, legs, fvgs))
    breakers = detect_breakers(obs, sweeps)
    log.info("obs_detected", count=len(obs), breakers=len(breakers))

    signals: list[Signal] = []
    if "unicorn" in cfg.setups:
        signals.extend(detect_unicorns(bars, breakers, fvgs, pools, config=cfg.unicorn))
    if "mss_fvg" in cfg.setups:
        signals.extend(detect_mss_fvg(bars, mss_events, fvgs, pools, config=cfg.mss_fvg))
    if "ob_ote" in cfg.setups:
        signals.extend(detect_ob_ote(bars, obs, pools, config=cfg.ob_ote))
    if "silver_bullet" in cfg.setups:
        signals.extend(detect_silver_bullet(bars, fvgs, pools, config=cfg.silver_bullet))
    log.info("signals_total", count=len(signals))
    return signals


def run_pipeline(
    bars: Bars,
    *,
    pipeline_config: PipelineConfig | None = None,
    backtest_config: BacktestConfig | None = None,
) -> BacktestResult:
    signals = detect_all_signals(bars, cfg=pipeline_config)
    result = run_backtest(bars, signals, config=backtest_config)
    return result
