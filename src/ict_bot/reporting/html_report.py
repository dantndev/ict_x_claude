"""HTML report builder — single self-contained file per backtest run."""

from __future__ import annotations

import base64
import json
from collections.abc import Sequence
from pathlib import Path

from ict_bot.backtest.portfolio import Portfolio
from ict_bot.reporting.metrics import Metrics, compute_metrics
from ict_bot.reporting.plots import (
    drawdown_curve,
    equity_curve,
    heatmap_day_hour,
    r_distribution,
)


def _img_b64(path: Path) -> str:
    if not path.exists():
        return ""
    raw = path.read_bytes()
    return f"data:image/png;base64,{base64.b64encode(raw).decode()}"


_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Backtest report — {run_id}</title>
<style>
  body {{ font-family: ui-sans-serif, system-ui, sans-serif; margin: 24px; color: #222; }}
  h1 {{ margin-top: 0; }}
  table.metrics {{ border-collapse: collapse; margin: 12px 0 24px; }}
  table.metrics td, table.metrics th {{ border: 1px solid #ddd; padding: 6px 12px; }}
  table.metrics th {{ background: #f6f6f6; text-align: left; }}
  img {{ max-width: 100%; border: 1px solid #eee; margin: 12px 0; }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }}
  pre {{ background: #f6f6f6; padding: 12px; border-radius: 6px; overflow: auto; }}
</style>
</head>
<body>
<h1>Backtest report — {run_id}</h1>
<p><strong>Range:</strong> {first_ts} → {last_ts} &nbsp; <strong>Bars:</strong> {n_bars}</p>

<h2>Metrics</h2>
<table class="metrics">
<tr><th>Trades</th><td>{n_trades}</td><th>Win rate</th><td>{win_rate}</td></tr>
<tr><th>Avg win</th><td>{avg_win}</td><th>Avg loss</th><td>{avg_loss}</td></tr>
<tr><th>Profit factor</th><td>{pf}</td><th>Expectancy R</th><td>{exp_r}</td></tr>
<tr><th>Total PnL</th><td>{total_pnl}</td><th>Final equity</th><td>{final_equity}</td></tr>
<tr><th>Max drawdown</th><td>{dd_usd} ({dd_pct})</td><th>Sharpe / Sortino</th><td>{sharpe} / {sortino}</td></tr>
</table>

<div class="grid">
  <div>
    <h3>Equity curve</h3>
    {equity_img}
  </div>
  <div>
    <h3>Drawdown</h3>
    {dd_img}
  </div>
  <div>
    <h3>R-multiple distribution</h3>
    {r_img}
  </div>
  <div>
    <h3>PnL heatmap (weekday × hour)</h3>
    {heat_img}
  </div>
</div>

<h2>Setup breakdown</h2>
<pre>{setup_breakdown}</pre>

<h2>Skipped signals</h2>
<pre>{skipped}</pre>
</body>
</html>
"""


def _img_tag(path: Path) -> str:
    src = _img_b64(path)
    return f'<img src="{src}" alt="plot">' if src else "<em>plot unavailable</em>"


def build_html_report(
    portfolio: Portfolio,
    out_dir: Path,
    *,
    run_id: str,
    first_ts: object,
    last_ts: object,
    n_bars: int,
    skipped_signals: int,
    reasons_skipped: dict[str, int],
) -> Path:
    metrics: Metrics = compute_metrics(portfolio)
    equity_vals: Sequence[float] = [e for _, e in portfolio.equity_series]
    r_vals: Sequence[float] = [t.r_multiple for t in portfolio.trades]
    heat_rows = [
        (t.entry_ts_ny.weekday(), t.entry_ts_ny.hour, t.pnl_usd)
        for t in portfolio.trades
    ]

    eq_path = out_dir / "equity.png"
    dd_path = out_dir / "drawdown.png"
    r_path = out_dir / "r_dist.png"
    heat_path = out_dir / "heatmap.png"
    equity_curve(equity_vals, eq_path)
    drawdown_curve(equity_vals, dd_path)
    r_distribution(r_vals, r_path)
    heatmap_day_hour(heat_rows, heat_path)

    setup_counts: dict[str, dict[str, float]] = {}
    for t in portfolio.trades:
        rec = setup_counts.setdefault(t.setup_name, {"n": 0, "pnl": 0.0, "r_sum": 0.0})
        rec["n"] += 1
        rec["pnl"] += t.pnl_usd
        rec["r_sum"] += t.r_multiple

    pf_str = (f"{metrics.profit_factor:.2f}" if metrics.profit_factor != float("inf")
              else "∞")
    html = _HTML.format(
        run_id=run_id,
        first_ts=str(first_ts),
        last_ts=str(last_ts),
        n_bars=n_bars,
        n_trades=metrics.n_trades,
        win_rate=f"{metrics.win_rate:.1%}",
        avg_win=f"${metrics.avg_win_usd:,.2f}",
        avg_loss=f"${metrics.avg_loss_usd:,.2f}",
        pf=pf_str,
        exp_r=f"{metrics.expectancy_r:+.2f}R",
        total_pnl=f"${metrics.total_pnl_usd:,.2f}",
        final_equity=f"${metrics.final_equity:,.2f}",
        dd_usd=f"${metrics.max_drawdown_usd:,.2f}",
        dd_pct=f"{metrics.max_drawdown_pct:.1%}",
        sharpe=f"{metrics.sharpe:.2f}",
        sortino=f"{metrics.sortino:.2f}",
        equity_img=_img_tag(eq_path),
        dd_img=_img_tag(dd_path),
        r_img=_img_tag(r_path),
        heat_img=_img_tag(heat_path),
        setup_breakdown=json.dumps(setup_counts, indent=2),
        skipped=f"total={skipped_signals}\nreasons={json.dumps(reasons_skipped, indent=2)}",
    )
    out_path = out_dir / "report.html"
    out_path.write_text(html, encoding="utf-8")
    return out_path
