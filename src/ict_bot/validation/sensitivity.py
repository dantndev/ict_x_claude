"""Parameter-sensitivity sweep over the pipeline thresholds."""

from __future__ import annotations

from dataclasses import dataclass, field

from ict_bot.backtest.engine import BacktestConfig
from ict_bot.backtest.runner import PipelineConfig, run_pipeline
from ict_bot.data.models import Bars
from ict_bot.reporting.metrics import Metrics, compute_metrics
from ict_bot.signals.imbalance.fvg import FVGConfig
from ict_bot.signals.setups.mss_fvg import MssFvgConfig
from ict_bot.signals.setups.ob_ote import ObOteConfig
from ict_bot.signals.setups.silver_bullet import SilverBulletConfig
from ict_bot.signals.setups.unicorn import UnicornConfig
from ict_bot.structure.displacement import DisplacementConfig


@dataclass(frozen=True, slots=True)
class SensitivityPoint:
    body_atr_min: float
    body_range_min: float
    min_rr: float
    metrics: Metrics


@dataclass(slots=True)
class SensitivityResult:
    points: list[SensitivityPoint] = field(default_factory=list)

    def best_by_expectancy_r(self) -> SensitivityPoint | None:
        if not self.points:
            return None
        return max(self.points, key=lambda p: p.metrics.expectancy_r)

    def to_table(self) -> list[dict[str, float]]:
        return [
            {
                "body_atr_min": p.body_atr_min,
                "body_range_min": p.body_range_min,
                "min_rr": p.min_rr,
                "n_trades": float(p.metrics.n_trades),
                "expectancy_r": p.metrics.expectancy_r,
                "total_pnl_usd": p.metrics.total_pnl_usd,
                "max_dd_pct": p.metrics.max_drawdown_pct,
            }
            for p in self.points
        ]


def sweep_displacement(
    bars: Bars,
    *,
    body_atr_grid: tuple[float, ...] = (1.0, 1.25, 1.5, 1.75),
    body_range_grid: tuple[float, ...] = (0.4, 0.6),
    min_rr_grid: tuple[float, ...] = (1.0, 1.5, 2.0),
    backtest_config: BacktestConfig | None = None,
) -> SensitivityResult:
    """Grid sweep over (body_atr_min, body_range_min, min_rr)."""
    bcfg = backtest_config or BacktestConfig()
    out = SensitivityResult()
    for atr in body_atr_grid:
        for br in body_range_grid:
            for rr in min_rr_grid:
                pcfg = PipelineConfig(
                    displacement=DisplacementConfig(
                        atr_lookback=14, body_atr_min=atr, body_range_min=br,
                    ),
                    fvg=FVGConfig(require_displacement=True, min_gap_ticks=1,
                                  tick_size=0.25),
                    unicorn=UnicornConfig(min_rr=rr),
                    mss_fvg=MssFvgConfig(min_rr=rr),
                    ob_ote=ObOteConfig(min_rr=rr),
                    silver_bullet=SilverBulletConfig(min_rr=rr),
                )
                res = run_pipeline(bars, pipeline_config=pcfg, backtest_config=bcfg)
                metrics = compute_metrics(res.portfolio)
                out.points.append(
                    SensitivityPoint(
                        body_atr_min=atr,
                        body_range_min=br,
                        min_rr=rr,
                        metrics=metrics,
                    ),
                )
    return out
