"""Walk-forward validation with embargo (purged-CV friendly).

Splits the bars into N rolling (train, test) windows. For each:
    1. (optional) refit pipeline parameters using only the train window.
    2. Run the pipeline on the test window and compute metrics.
The result is the test-window concatenated equity + per-fold metrics, so the
caller can compare "in-sample vs out-of-sample" expectancy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ict_bot.backtest.engine import BacktestConfig
from ict_bot.backtest.runner import PipelineConfig, run_pipeline
from ict_bot.data.models import Bars
from ict_bot.reporting.metrics import Metrics, compute_metrics


@dataclass(frozen=True, slots=True)
class WalkForwardFold:
    fold_index: int
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    metrics: Metrics


@dataclass(slots=True)
class WalkForwardResult:
    folds: list[WalkForwardFold] = field(default_factory=list)

    @property
    def n_folds(self) -> int:
        return len(self.folds)

    def aggregate_expectancy_r(self) -> float:
        rs = [f.metrics.expectancy_r for f in self.folds]
        return sum(rs) / len(rs) if rs else 0.0

    def aggregate_total_pnl(self) -> float:
        return sum(f.metrics.total_pnl_usd for f in self.folds)


def walk_forward(
    bars: Bars,
    *,
    n_folds: int = 5,
    train_ratio: float = 0.6,
    embargo_bars: int = 60,
    pipeline_config: PipelineConfig | None = None,
    backtest_config: BacktestConfig | None = None,
) -> WalkForwardResult:
    """Rolling walk-forward over the bars."""
    if bars.empty or n_folds < 1:
        return WalkForwardResult()
    first = bars.first_ts()
    last = bars.last_ts()
    assert first is not None and last is not None
    total_span = last - first
    fold_span = total_span / n_folds

    result = WalkForwardResult()
    for i in range(n_folds):
        seg_start = first + fold_span * i
        seg_end = first + fold_span * (i + 1)
        # Within this segment, train_ratio leads, then embargo, then test
        train_end = seg_start + (seg_end - seg_start) * train_ratio
        test_start = train_end + timedelta(minutes=embargo_bars)
        if test_start >= seg_end:
            continue
        # NOTE: PipelineConfig is currently static; we still scope detection
        # to the test window so that the backtest runs purely out-of-sample.
        test_bars = bars.slice(test_start, seg_end)
        if test_bars.empty:
            continue
        result_test = run_pipeline(
            test_bars,
            pipeline_config=pipeline_config,
            backtest_config=backtest_config,
        )
        metrics = compute_metrics(result_test.portfolio)
        result.folds.append(
            WalkForwardFold(
                fold_index=i,
                train_start=seg_start,
                train_end=train_end,
                test_start=test_start,
                test_end=seg_end,
                metrics=metrics,
            ),
        )
    return result
