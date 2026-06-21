"""Reporting: metrics, plots, HTML report."""

from ict_bot.reporting.html_report import build_html_report
from ict_bot.reporting.metrics import Metrics, compute_metrics, format_metrics
from ict_bot.reporting.plots import (
    drawdown_curve,
    equity_curve,
    heatmap_day_hour,
    r_distribution,
)

__all__ = [
    "Metrics",
    "build_html_report",
    "compute_metrics",
    "drawdown_curve",
    "equity_curve",
    "format_metrics",
    "heatmap_day_hour",
    "r_distribution",
]
