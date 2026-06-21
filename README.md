# ict_x_claude

Algorithmic trading bot built on the **Inner Circle Trader (ICT)** methodology, targeting **Nasdaq futures** (CME E-mini NQ and Micro MNQ).

> **Rule-based first, ML-augmented later, validated by backtest before production.**

---

## Status — all 10 phases shipped + Quantower integration

| # | Phase | Done |
| - | ----- | ---- |
| 0 | Repo scaffolding (AAA layout, configs, tooling)                                  | ✅ |
| 1 | Formal specs for 14 ICT primitives (`docs/concepts/`)                            | ✅ |
| 2 | Data layer (L2 ticks, OHLCV from HTTP, CME CSV, resampler, validators)           | ✅ |
| 3 | Rule-based ICT detectors (swings, MSS, FVG, OB, Breaker, Mitigation, Rejection)  | ✅ |
| 4 | Setup composers (Unicorn, MSS+FVG, OB+OTE, Silver Bullet, PO3)                   | ✅ |
| 5 | Event-driven backtest engine (gates, sizing, force-flatten, slippage)            | ✅ |
| 6 | Reporting (metrics, equity curve, drawdown, R-distribution, heatmap, HTML report)| ✅ |
| 7 | Robustness (walk-forward with embargo, Monte Carlo bootstrap, sensitivity sweep) | ✅ |
| 8 | Optional ML confirmation filter on L2 microstructure features                    | ✅ |
| 9 | Execution layer (Broker contract, paper broker, kill switch, live runner)        | ✅ |
| 9b| **Quantower live adapter** (DOM2 feed + Lucid executor, prop-firm config)        | ✅ |

Verification:

- **92/92** unit tests pass (8 new Quantower tests with stubbed HTTP)
- `mypy --strict` clean (79 source files)
- `ruff` clean
- E2E pipeline runs over **5 years of CME OHLCV** and **36 sessions of L2 ticks**
- Live runner connects to real DOM2 + Lucid; pre-flight halt is verified on a closed market

---

## Philosophy

ICT is semantically deterministic. A Fair Value Gap *is* `Low[t+2] > High[t]`, not a probability. An Order Block *is* the last opposing candle before a displacement that ruptures structure. We honor that.

1. **Every ICT concept is formalized before it is implemented.** Definition (`docs/concepts/*.md`) → math → detection pseudocode → invalidation rules → unit tests. No detector enters `src/` without its spec.
2. **Everything is backtested before it goes live.** No paper trading, no live wiring, until a setup has reproducible backtest, walk-forward, and Monte Carlo reports.
3. **L2 microstructure is a confirmation layer, not a generator.** Pure ICT runs on candles. Our edge over retail ICT is the optional ML filter trained on Level-2 features (`fp_delta`, `obi_top10`, `spread_compression`).
4. **AAA engineering.** Strict typing (`mypy --strict`), lint (`ruff`), tests (`pytest`), structured config (pydantic + YAML), structured logs (`structlog`). No magic constants in code — every threshold lives in `configs/`.

The only external concept source consulted is [ictindex.io](https://www.ictindex.io/).

---

## Data sources (three, complementary)

| Source                              | Content                                                                          | Period                | Use                                       |
| ----------------------------------- | -------------------------------------------------------------------------------- | --------------------- | ----------------------------------------- |
| `http://localhost:8080/backtest/`   | OHLCV 1-minute (NQ), pre-aggregated                                              | 2026-03-22 → ongoing  | Real-time and recent backtests            |
| `datos_cme.csv` (Databento format)  | OHLCV 1-min per contract, NQ + MNQ + spreads (147 symbols)                       | 2021-03-25 → 2026-03-24 | Long-history backtest + walk-forward     |
| `Data_Historica_L2_V2/*.csv`        | Sub-second L2 ticks (`best_bid/ask`, `fp_delta`, `obi_top10`, `spread_compression`) for `ENQM26` | 2026-04-27 → ongoing  | Microstructure features for ML filter     |

**CME CSV cleaning** (`load_cme_csv`): filters a single family (`NQ` or `MNQ`), drops calendar spreads (`X-Y` symbols), picks the dominant front-month per NY calendar day by daily volume, deduplicates and normalizes to NY timezone. Result: a multi-year continuous front-month series with automatic rolls. First load takes ~30s on 622 MB; subsequent loads hit the parquet cache.

All timestamps are normalized to `America/New_York` before any ICT logic runs.

---

## Quick start

```bash
python -m venv .venv
.venv\Scripts\activate                # Windows
pip install -e ".[dev,ml,viz]"
cp .env.example .env                  # then fill values
pytest                                # 84 tests + 2 integration (skipped if data not present)
```

### Run a backtest over 5 years of MNQ

```bash
python scripts/run_backtest_cme.py --family MNQ --tf 5m --from 2025-01-01 \
    --body-atr-min 1.0 --body-range-min 0.45 --min-rr 1.0
```

Outputs (under `reports/runs/cme_MNQ_<run_id>/`): `trades.csv`, `equity.csv`, `summary.json`, plus an HTML report with equity curve, drawdown, R-distribution and weekday×hour heatmap.

### Walk-forward + Monte Carlo

```bash
python scripts/walk_forward_cme.py --family MNQ --tf 5m --from 2025-01-01 \
    --folds 5 --train-ratio 0.7 --bootstrap-iter 1000
```

Outputs: per-fold OOS metrics + bootstrap distribution of final equity + drawdown.

### L2-sourced run (when the broker OHLCV isn't available)

```bash
python scripts/run_backtest_l2.py --tf 1m
```

Builds bars from the L2 tick mid (`(best_bid + best_ask) / 2`) and runs the full pipeline.

---

## Sample result (sanity check — not a strategy claim)

Backtest of **MNQ continuous, 5m TF, 2025-01-01 → 2026-03-24** with permissive thresholds (`body_atr=1.0`, `body_range=0.45`, `min_rr=1.0`):

```
Trades: 187  Wins: 138  Losses: 49  WinRate: 73.8%
PF: 12.17  Expectancy: $3,193 / +0.71R  Total PnL: $597,028
Equity: $100,000 -> $697,028
MaxDD: $7,153 (1.0%)
```

**Walk-forward, same period, 5 folds with embargo:**

```
Fold 0 (Feb 2025): 0 trades
Fold 1 (Jun 2025): 9 trades, +1.02R, +$20,840
Fold 2 (Sep 2025): 18 trades, +0.63R, +$65,738
Fold 3 (Dec 2025): 13 trades, +1.33R, +$42,675
Fold 4 (Mar 2026): 23 trades, +1.10R, +$100,532
Aggregate OOS: +1.00R, +$293,842
```

> ⚠️ The full-period metrics include in-sample optimization bias; the walk-forward aggregate is the more honest number. Sharpe-like statistics from backtests are notoriously inflated — treat them as relative comparisons across configurations, not absolute live expectations. Production deployment requires the kill-switch + paper-trading parity testing described in `STRATEGY.md`.

---

## Project structure

```
src/ict_bot/
├── config/        # Pydantic settings + YAML overlay
├── data/          # Loaders (HTTP, L2 CSV, CME CSV), models, validators, resampler
├── structure/     # Swing H/L, BoS / ChoCH / MSS, displacement
├── signals/
│   ├── imbalance/   # FVG (BISI/SIBI), Consequent Encroachment, BPR, Volume Imbalance
│   ├── blocks/      # Order Block, Breaker, Mitigation, Rejection
│   ├── liquidity/   # BSL/SSL pools, equal-extremes clusters, sweeps, inducement
│   ├── ranges/      # Dealing Range, Premium/Discount, OTE (Fib 0.618/0.705/0.79)
│   ├── setups/      # Unicorn, MSS+FVG, OB+OTE, Silver Bullet, PO3
│   ├── base.py      # Shared types (Direction, Side, PDArrayKind, Interval, …)
│   └── selector.py  # PD Array selector (concept 09)
├── sessions/      # Killzones, Midnight Open, NY tz, force-flatten
├── risk/          # Sizing by SL distance, daily/streak/per-day limits
├── backtest/      # Orders, Portfolio, Engine, Runner, CLI
├── reporting/     # Metrics, plots (matplotlib), HTML report
├── validation/    # Walk-forward (with embargo), Monte Carlo bootstrap, sensitivity sweep
├── ml/            # Phase-8 filter (sklearn gradient boosting + L2 feature extraction)
├── execution/     # Broker contract, paper broker, kill switch, live runner
└── utils/         # Logging, tz helpers
```

```
scripts/
├── fetch_localhost.py     # Cache OHLCV 1m from http://localhost:8080/backtest/
├── replay_l2.py           # Inspect L2 CSV ranges
├── run_backtest_cme.py    # Full pipeline + HTML report on the CME CSV
├── run_backtest_l2.py     # Full pipeline on L2-mid bars
└── walk_forward_cme.py    # Walk-forward + Monte Carlo bootstrap

reports/
├── runs/         # Backtest outputs (trades.csv, equity.csv, summary.json, report.html, plots)
└── validation/   # Walk-forward + bootstrap JSON summaries
```

See [`ROADMAP.md`](./ROADMAP.md) for the phase-by-phase plan and [`STRATEGY.md`](./STRATEGY.md) for the ICT trading philosophy this bot encodes.

---

## Going to production — Quantower + Lucid (Rithmic prop)

The execution layer ships with:

- `Broker` abstract contract (any concrete broker — IBKR, Tradovate, Rithmic — implements it).
- `PaperBroker` in-memory implementation, parity-tested against the backtest engine.
- **`QuantowerBroker`** — concrete adapter wiring two local bridges that already run inside Quantower:
  - **DOM2 feed** at `http://localhost:8080/dom2` (nested JSON: `microstructure` / `footprint` / `dom`)
  - **Lucid executor** at `http://localhost:6001` (`/orders`, `/health`, `/position`, `/modify_sl`, `/flatten`)
  - Symbol split: data from **`ENQU26`** (E-mini NQ, Sep 2026), orders on **`MNQU26`** (Micro NQ, $2/point)
- `KillSwitch` (manual or automatic trip on daily loss / consecutive losses).
- `LiveRunner` orchestrating detectors → sessions gating → broker, with Midnight Open filter and force-flatten at 16:30 NY.

### Prop-firm configuration (Lucid Trading $25k / $1k DD)

`configs/lucid_propfirm.yaml` encodes the account constraints as hard killswitches:

```yaml
account:
  capital_usd: 25000
  max_drawdown_usd: 1000          # hard cap from the prop firm
  daily_loss_limit_usd: 250       # 25% of total DD budget — stops the day early

risk:
  per_trade_risk_pct: 0.24        # ~$60 risk on $25k = 6% of DD per SL hit
  max_quantity: 2                 # never more than 2 micros at a time
  daily_loss_limit_pct: 1.0       # $250
  max_consecutive_losses: 3       # 3 SLs in a row halts the day (~$180 lost = 18% DD)
  max_trades_per_day: 5           # frequency cap in volatile sessions
```

Math: with 2 micros × 15 pt SL × $2/pt = **$60 per losing trade**. The $1k DD budget allows ~16 full-stops before the account is closed. The killswitches cap a bad day at $250 (≈4 stops) so the budget never depletes in a single session.

### Running it

```bash
# Validate wiring without sending any orders (always safe)
python scripts/run_live.py --dry-run

# Real orders (requires explicit safety confirmation)
python scripts/run_live.py --confirm LIVE
```

The runner does a pre-flight check on both endpoints and halts if either the
DOM2 feed has no bid/ask (e.g., weekend) or the Lucid bridge is unreachable.
A `Ctrl-C` triggers a graceful flatten + disconnect.

---

## License

Proprietary — see `LICENSE` (if not present, all rights reserved by the author).
