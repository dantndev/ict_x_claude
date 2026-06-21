"""Plots for backtest reports.

Matplotlib is an optional dependency (installed via `pip install -e .[viz]`).
Each function returns a Path to the saved PNG (or None when matplotlib is
not available — the caller logs a warning and skips).
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from ict_bot.utils.logging import get_logger

log = get_logger(__name__)


def _try_import_matplotlib() -> object | None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        return matplotlib
    except ImportError:
        log.warning("matplotlib_unavailable",
                    hint="pip install -e '.[viz]' to enable plots")
        return None


def equity_curve(equity: Sequence[float], out_path: Path) -> Path | None:
    mpl = _try_import_matplotlib()
    if mpl is None:
        return None
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(range(len(equity)), equity, color="#0f6cbf", linewidth=1.2)
    ax.set_title("Equity curve")
    ax.set_xlabel("Bar index")
    ax.set_ylabel("Equity (USD)")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return out_path


def drawdown_curve(equity: Sequence[float], out_path: Path) -> Path | None:
    mpl = _try_import_matplotlib()
    if mpl is None or not equity:
        return None
    import matplotlib.pyplot as plt

    peak = equity[0]
    dd_series = []
    for e in equity:
        peak = max(peak, e)
        dd_series.append((peak - e) / peak * 100.0 if peak > 0 else 0.0)

    fig, ax = plt.subplots(figsize=(10, 3))
    ax.fill_between(range(len(dd_series)), dd_series, 0, color="#c0392b", alpha=0.5)
    ax.set_title("Drawdown (%)")
    ax.set_xlabel("Bar index")
    ax.set_ylabel("Drawdown %")
    ax.invert_yaxis()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return out_path


def r_distribution(r_multiples: Sequence[float], out_path: Path) -> Path | None:
    mpl = _try_import_matplotlib()
    if mpl is None or not r_multiples:
        return None
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.hist(r_multiples, bins=30, color="#2c7a7b", edgecolor="#1a4d4e")
    ax.axvline(0, color="black", linewidth=0.8)
    ax.set_title("R-multiple distribution")
    ax.set_xlabel("R")
    ax.set_ylabel("Count")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return out_path


def heatmap_day_hour(
    rows: list[tuple[int, int, float]],   # (weekday, hour, pnl)
    out_path: Path,
) -> Path | None:
    """Heatmap of summed PnL by weekday × hour."""
    mpl = _try_import_matplotlib()
    if mpl is None or not rows:
        return None
    import matplotlib.pyplot as plt

    grid = [[0.0 for _ in range(24)] for _ in range(7)]
    for wd, hr, pnl in rows:
        grid[wd][hr] += pnl
    fig, ax = plt.subplots(figsize=(10, 3))
    im = ax.imshow(grid, aspect="auto", cmap="RdYlGn")
    ax.set_yticks(range(7))
    ax.set_yticklabels(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
    ax.set_xticks(range(0, 24, 2))
    ax.set_xlabel("Hour (NY)")
    ax.set_title("PnL heatmap — weekday × hour")
    fig.colorbar(im, ax=ax, label="USD")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return out_path
