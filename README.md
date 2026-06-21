# ict_x_claude

Algorithmic trading bot built on the **Inner Circle Trader (ICT)** methodology, targeting **Nasdaq futures** (CME E-mini NQ and Micro MNQ).

> **Rule-based first, ML-augmented later, validated by backtest before production.**

---

## Status — Production-ready (Silver Bullet mode B on Lucid prop)

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
| 9b| Quantower live adapter (DOM2 feed + Lucid executor, prop-firm config)            | ✅ |
| 9c| Telegram remote control (notifier + commander, /status /pause /flatten ...)      | ✅ |
| P1| Pilot 001 — threshold sensitivity sweep                                          | ✅ |
| P2| Pilot 002 — fixed-R TP strategy added to all setups                              | ✅ |
| P3| Pilot 003 — walk-forward of 3 fixed-R candidates → winner A_max_freq             | ✅ |
| P4| Pilot 004 — per-killzone breakdown (87% of edge in Silver Bullet windows)        | ✅ |
| P5| Pilot 005 — session-mode comparison (B beats A/C on every risk metric)           | ✅ |
| Px| **Production hardening** — news_block fix, max_losses=10, shadow logger          | ✅ |

Verification:

- **102/102** unit tests pass
- `mypy --strict` clean (83 source files)
- `ruff` clean
- E2E pipeline runs over **5 years of CME OHLCV** and **36 sessions of L2 ticks**
- Live runner connects to real DOM2 + Lucid; pre-flight halt is verified on a closed market
- Production config in `configs/lucid_propfirm.yaml` reflects pilot 005 winner

## Currently deployed parameters

Based on the pilots 001-006 (`docs/pilots/`), the production config trades
exclusively in the two **Silver Bullet** windows — the ICT-canonical
"macros" where the bot captures **87% of historical PnL** with **35% of the
trades** vs the all-killzone baseline. Pilot 006 confirmed that **1-minute
bars** beat the 5m/15m alternatives on `trades/day × expectancy_R`, at the
cost of a slightly worse OOS R (+0.55 vs +0.88 for 5m).

```yaml
# configs/lucid_propfirm.yaml
account:
  capital_usd: 25000.0
  max_drawdown_usd: 1000.0
  data_symbol: ENQU26
  exec_symbol: MNQU26

setups:
  tf: 1m                          # pilot 006 winner — 5x more trades/day
  body_atr_min: 1.0
  body_range_min: 0.5
  tp_strategy: fixed_R
  fixed_tp_r: 1.5

execution:
  allowed_windows:                # Silver Bullet ONLY (pilot 005 winner)
    - silver_bullet_am            # 10:00-11:00 NY
    - silver_bullet_pm            # 14:00-15:00 NY

risk:
  max_consecutive_losses: 6       # pre-empts pilot 006's worst streak of 7
  max_trades_per_day: 8           # 1m mode does ~1.83/day; 8 is safety cap
  daily_loss_limit_pct: 1.0       # $250 hard daily cap
```

Backtest expectation with this config on 1m bars (2024-01 → 2026-03,
IS-biased, treat as direction not magnitude):

- 1490 trades, **60% win rate**, +1.17 R/trade
- ~1.83 trades/day (≈ 5/week)
- MaxDD 0.30%, bootstrap p95 DD 5.92%
- WF 8/8 folds OOS positive, aggregate +0.55R
- Realistic live projection with 2 micros: **~$38/day net**, reaching the
  $1,250 evaluation target in **~6-7 weeks**

## Shadow signal logger (analyze mode A/C while running mode B)

`logs/shadow/<YYYY-MM-DD>.csv` is written for **every** signal the bot
detects in live, regardless of whether it executed. Each row carries
`in_mode_A`, `in_mode_B`, `in_mode_C` flags + the killzone tag + the
skip reason. So you can answer at any time:

- "If I had switched to mode C this week, how many extra trades?"
- "Which killzone is producing the most rejected signals now?"
- "Did the win rate of SB stay constant after a regime change?"

…without re-running any backtest. The logger is thread-safe and never
blocks the trading loop.

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
| `data/cme_nq_2021_2026/datos_cme.csv` (Databento format) | OHLCV 1-min per contract, NQ + MNQ + spreads (147 symbols) | 2021-03-25 → 2026-03-24 | Long-history backtest + walk-forward |
| `data/Data_Historica_L2_V2/*.csv`   | Sub-second L2 ticks (`best_bid/ask`, `fp_delta`, `obi_top10`, `spread_compression`) for `ENQM26` | 2026-04-27 → ongoing  | Microstructure features for ML filter     |
| `http://localhost:8080/dom2`        | Quantower DOM2 bridge: microstructure + footprint + DOM top-40                   | live                  | LIVE data feed for `QuantowerBroker`      |
| `http://localhost:6001/*`           | Quantower → Lucid (Rithmic) executor bridge                                      | live                  | LIVE order routing                        |

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

Quick start (open VSCode in the repo root and press **F5** to pick one):

| Launcher (`.vscode/launch.json`) | When to use |
| -------------------------------- | ----------- |
| **Bot — Dry-run** | First test of the day. Connects to both bridges, runs the loop, no real orders. |
| **Bot — LIVE ⚠** | Real orders, single process. If it crashes you have to restart manually. |
| **Bot — Supervised LIVE ⚠** | Real orders **wrapped by the supervisor** — auto-restarts on `/restart` and on crashes (up to 5 per 10 min). **Production mode.** |

Or from the terminal:

```powershell
.\.venv\Scripts\activate
python scripts/supervisor.py --confirm LIVE      # production
python scripts/run_live.py --dry-run             # safe wiring test
```

The pre-flight halts the runner if either DOM2 feed has no bid/ask
(e.g., weekend) or the Lucid bridge is unreachable. `Ctrl-C` triggers a
graceful flatten + disconnect.

**Read [`docs/OPERATING.md`](docs/OPERATING.md) for the full daily-ops guide**:
what the bot does hour by hour, where to look when something fails, how the
supervisor and the shadow log work.

### Remote control via Telegram

`TelegramNotifier` (push alerts) + `TelegramCommander` (long-poll listener
restricted to a single authorized `chat_id`) are wired into `scripts/run_live.py`
out of the box. Credentials come from `TELEGRAM_TOKEN` and `TELEGRAM_CHAT_ID`
in `.env` (already in `.env.example`). When the bot starts, it registers the
command menu in the chat (`/` button shows the clickable list).

Commands (only honored from the authorized chat):

| Command   | Effect |
| --------- | ------ |
| `/status` | Reports paused state, kill-switch state, open positions, equity |
| `/pause`  | Stop taking new entries (existing positions keep their SL/TP) |
| `/resume` | Re-enable entries |
| `/flatten`| Close all open positions immediately via `broker.flatten_all()` |
| `/stop`   | Clean shutdown of the loop (positions left to their brackets) |
| `/restart`| Flatten + exit with code 42 (for a supervisor to relaunch) |

The notifier publishes: `[START] / [STOP] / [TRADE] / [CERRADO] / [KILLSWITCH] / [ERROR] / [WARN]`
plus the command-feedback events `[CMD OK] / [PAUSE] / [RESUME] / [FLATTEN]`.
Notifications are fire-and-forget on a daemon thread — they never block the
trading loop, even when Telegram's API is slow or rate-limits us.

If `TELEGRAM_TOKEN` / `TELEGRAM_CHAT_ID` are absent, both modules become
silent no-ops; the bot still trades.

---

## Pilot experiments — improvements grounded in data + ICT (no inventions)

Independent scripts that test specific changes against the 5-year CME data to
quantify their effect on **frequency vs edge** before touching the production
config. Each pilot writes its artifacts under `reports/pilots/<run_id>/`.

### Pilots — finished

Each pilot is independent and re-runnable. Full reports in `docs/pilots/`.

| # | Pilot | Outcome | Doc |
| - | ----- | ------- | --- |
| 001 | Threshold sensitivity sweep (27 cells) | Found `min_rr=1.5` was a hidden cap. Plateau at `(body_atr=1.0, body_range=0.5, min_rr=1.0)`. | `docs/pilots/001_sensitivity_sweep.md` |
| 002 | Fixed-R TP strategy added to all setups | Fixed-R beats nearest_pool across the frontier. `min_rr` becomes redundant under fixed_R. Best cells: `(1.0, 0.5, fixed=1.5)` and `(1.5, 0.5, fixed=2.0)`. | `docs/pilots/002_fixed_tp.md` |
| 003 | Walk-forward of 3 fixed-R candidates | Winner = `(1.0, 0.5, fixed_tp_r=1.5)`. 8/8 folds positive, +0.86R OOS. Bug fix shipped (`LimitsState.reset_for_day` was leaking streak lock across days). | `docs/pilots/003_wf_candidates.md` |
| 004 | Per-killzone PnL breakdown (winner cell) | **87% of all PnL** concentrated in Silver Bullet AM + PM. NY PM "net" has negative expectancy. London adds 2% of PnL with 22% of trades. | `docs/pilots/004_session_breakdown.md` |
| 005 | Session-mode comparison (A vs B vs C) | **Mode B (Silver Bullet only) wins every risk metric**: MaxDD halved, p95 DD ~1/3, worst trade -40%, max consec losers 3 vs 6. Promoted to production. | `docs/pilots/005_session_mode_comparison.md` |
| 006 | TF sweep on mode B (1m/3m/5m/15m) | **1m wins on tr/day × exp_R = 2.149** (4.4× the 5m baseline). Slight OOS R degradation (+0.55 vs +0.88) is the trade-off. Caught a latent live↔backtest mismatch (live always ran 1m; backtest defaulted to 5m). Promoted 1m to production. | `docs/pilots/006_tf_sweep.md` |

Scripts: `scripts/pilot_sensitivity_sweep.py`, `scripts/pilot_fixed_tp.py`,
`scripts/pilot_003_wf_candidates.py`, `scripts/pilot_004_session_breakdown.py`,
`scripts/pilot_005_mode_comparison.py`.

### Pilot menu — open ideas (not yet executed)

| # | Change                                                | Hypothesis            | Risk    |
| - | ----------------------------------------------------- | --------------------- | ------- |
| 005b | Same 3 session modes on 1m / 3m timeframes          | Frequency uplift × ?  | medium  |
| 006 | Activate Rejection / Mitigation / BPR / Inducement / VolImb setups | +50-80% signals | low |
| 007 | Allow concurrent positions (lift single-position lock) | +20% trades          | high    |
| 008 | Multi-instrument (NQ + ES + YM)                       | up to 3×             | high    |
| 009 | Train ML filter on accumulated live shadow log + L2   | win-rate boost       | medium  |

Acceptance rule: only promote a change to production if it raises **OOS
expectancy_R or aggregate test PnL** in `walk_forward_cme.py` over the
multi-year CME series AND survives a session-mode comparison like pilot 005.

## L2 microstructure integration (where it lives, how to activate it)

The Level-2 tick stream (`Data_Historica_L2_V2/`) is integrated at two layers:

### As a data source for backtests

`scripts/run_backtest_l2.py` builds OHLCV bars from the L2 tick mid
(`(best_bid + best_ask) / 2`) and runs the full pipeline. This lets us test
the strategy *exactly* on the prices the live bridge sees — useful for
backtest↔live parity audits.

### As a feature extractor for the ML filter (Phase 8)

`ict_bot.ml.features.features_for_signal(signal, ticks, bars)` builds a
feature vector for every candidate signal:

- **Setup metadata:** which setup, side, RR, risk in points, confidence
- **Bar context:** ATR(14), hour-of-day, weekday
- **L2 microstructure window (±60 s around entry):**
  - `l2_fp_delta_mean` — net order flow in the entry window
  - `l2_obi_mean` — order-book imbalance top-10
  - `l2_spread_mean` — average spread (proxy for liquidity)
  - `l2_delta_accel_mean` — change of delta (momentum derivative)
  - `l2_spread_compression_mean` — relative spread tightness (LP confidence)

`ict_bot.ml.SignalFilter` wraps a gradient-boosting classifier; `train_filter`
fits it on `(features, win_label)` rows, `.accept(features)` returns the
go/no-go gate at inference. The filter is intentionally **NOT wired** into
`LiveRunner` by default because training needs >200 labeled signals from the
live bot. To enable it once you have data:

1. Run `scripts/run_backtest_l2.py` over your L2 days to collect signals.
2. Build training rows: `(features_for_signal(sig, ticks, bars), int(trade.pnl_usd > 0))`
3. `model = train_filter(rows); model.save(Path("checkpoints/filter.pkl"))`
4. In `scripts/run_live.py`, load the model and gate each signal before
   `runner.on_bars_window`:
   ```python
   from ict_bot.ml import SignalFilter, features_for_signal
   filt = SignalFilter.load(Path("checkpoints/filter.pkl"))
   # Inside the bar-close branch, filter signals before submitting:
   accepted = [s for s in signals
               if filt.accept(features_for_signal(s, latest_ticks_window, bars))]
   ```

The `latest_ticks_window` is what `LiveRunner` does *not* yet maintain — it
must be added (a rolling polars frame of L2 snapshots over the last ~5 min).
This is the only piece of plumbing needed to turn the filter on in live.

## License

Proprietary — see `LICENSE` (if not present, all rights reserved by the author).
