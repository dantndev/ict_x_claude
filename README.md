# ict_x_claude

Algorithmic trading bot built on the **Inner Circle Trader (ICT)** methodology, targeting **NQ futures** (CME E-mini Nasdaq-100, contract `ENQM26`).

> **Rule-based first, ML-augmented later, validated by backtest before production.**

---

## Philosophy

ICT is semantically deterministic. A Fair Value Gap *is* `Low[t+2] > High[t]`, not a probability. An Order Block *is* the last opposing candle before a displacement that ruptures structure. We honor that.

1. **Every ICT concept is formalized before it is implemented.** Definition (`docs/concepts/*.md`) → math → detection pseudocode → invalidation rules → unit tests. No detector enters `src/` without its spec.
2. **Everything is backtested before it goes live.** No paper trading, no live wiring, until a setup has a reproducible backtest report with edge metrics, drawdown, walk-forward, and Monte Carlo bootstrap.
3. **L2 microstructure is a confirmation layer, not a generator.** Pure ICT runs on candles. Our edge over retail ICT is using Level-2 data (`fp_delta`, `obi_top10`, `spread_compression`) to confirm entries.
4. **AAA engineering.** Strict typing (`mypy --strict`), lint (`ruff`), tests (`pytest`), structured config (pydantic + YAML), structured logs (`structlog`). No magic constants in code — every threshold lives in `configs/`.

The only external information source consulted for concept definitions is [ictindex.io](https://www.ictindex.io/).

---

## Data sources

| Source                              | Content                                  | Period                | Use                           |
| ----------------------------------- | ---------------------------------------- | --------------------- | ----------------------------- |
| `http://localhost:8080/backtest/`   | OHLCV 1-minute (NQ)                      | 2026-03-22 → ongoing  | Canonical bars for backtest   |
| `Data_Historica_L2_V2/*.csv`        | Sub-second L2 ticks (best bid/ask, footprint, OBI, delta, spread compression) for `ENQM26` | 2026-04-27 → ongoing  | Microstructure confirmation   |

All timestamps are normalized to `America/New_York` before any ICT logic runs (killzones, midnight open, sessions).

---

## Project structure

```
src/ict_bot/
├── config/      # Pydantic + YAML configuration
├── data/        # Loaders (L2, HTTP), validator, resampler, Bars/Ticks model
├── structure/   # Swing points, BoS, ChoCH, MSS, Displacement
├── signals/
│   ├── imbalance/   # FVG (BISI/SIBI), Consequent Encroachment, BPR, Volume Imbalance
│   ├── blocks/      # Order Block, Breaker, Mitigation, Rejection, Mean Threshold
│   ├── liquidity/   # BSL/SSL, equal H/L, sweep, inducement
│   ├── ranges/      # Dealing Range, Premium/Discount, OTE (Fib 0.62–0.79, 0.705)
│   └── setups/      # Unicorn, OB+OTE, Silver Bullet, MSS+FVG, PO3
├── sessions/    # Killzones, Midnight Open, NY tz, macros
├── risk/        # Sizing by SL distance, daily loss limit, max trades
├── backtest/    # Event-driven engine, slippage, commissions
├── execution/   # Broker adapters (paper → live)
├── reporting/   # Equity, drawdown, Sharpe/Sortino, R-distribution
├── ml/          # Phase 8: optional L2-based confirmation filter
└── utils/       # Logging, tz helpers, date utilities
```

See [`ROADMAP.md`](./ROADMAP.md) for the 10-phase plan and [`STRATEGY.md`](./STRATEGY.md) for the ICT trading philosophy this bot encodes.

---

## Setup (work-in-progress)

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows
pip install -e ".[dev,ml,viz]"
cp .env.example .env              # then fill values
pytest                            # currently: scaffolding only
```

---

## Status

**Phase 0 — Scaffolding.** No trading logic yet. The next phase formalizes each ICT concept with the user's sign-off before any detector is implemented.
