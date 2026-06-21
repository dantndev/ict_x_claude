# Roadmap — `ict_x_claude`

Ten phases. Each phase has an explicit definition of done; no phase advances without its predecessor.

| # | Phase | Done when... | Status |
| - | ----- | ------------ | ------ |
| 0 | **Bootstrap** — Repo scaffolding, configs, tooling, first commit | All directories, `pyproject.toml`, `.gitignore`, READMEs exist. Repo pushed to GitHub private. `pytest` runs. | ✅ |
| 1 | **Concept formalization** — One `docs/concepts/<concept>.md` per ICT primitive. | All 14 specs in the V1 catalog approved. | ✅ |
| 2 | **Data layer** — Loaders for L2 CSVs, HTTP OHLCV, **CME multi-year CSV (5 years, 5.4M rows, cleaned)**, validator, resampler, `Bars` / `Ticks` models. | Loading 3 months of OHLCV + L2 + 5 years of CME CSV in under 30s (first run); cached afterwards. | ✅ |
| 3 | **Detectors** — Pure implementations of formalized concepts. | Each detector passes its concept fixture; 84 tests passing. | ✅ |
| 4 | **Setups** — Composition into Unicorn, MSS+FVG, OB+OTE, Silver Bullet, PO3. | Each setup produces `Signal` objects with entry, SL, TP, confidence, audit. | ✅ |
| 5 | **Backtest engine** — Event-driven, NQ/MNQ-aware, commissions, slippage, SL/TP, session force-flatten, position sizing, daily-loss + streak locks. | Full backtest of 5 years of MNQ runs in seconds; outputs trades.csv + equity.csv + summary.json. | ✅ |
| 6 | **Reporting** — Metrics + matplotlib plots (equity, drawdown, R-distribution, weekday×hour heatmap) + self-contained HTML report. | One-click report from a backtest run. | ✅ |
| 7 | **Robustness** — Walk-forward with embargo, Monte Carlo bootstrap of trade order, sensitivity sweep over (body_atr, body_range, min_rr). | `scripts/walk_forward_cme.py` ships and produces per-fold OOS metrics + bootstrap CIs. | ✅ |
| 8 | **ML confirmation (optional)** — Filter trained on (signal_features + L2 microstructure) → P(win) ≥ threshold accepts. Compare PnL with/without filter. | `ict_bot.ml` package: `features_for_signal` + `SignalFilter` + `train_filter`. Discardable if no edge. | ✅ |
| 9 | **Production** — Broker abstract contract, paper-broker implementation, kill switch, live runner with killzone/news/lunch/midnight-open gating and force-flatten. | `ict_bot.execution` package ready. Choosing a concrete broker and N-session paper parity remain on the user. | ✅ |

---

## Status

All 10 phases shipped — see commits on `main`. Next, the work that remains is
*operational*, not architectural:

1. Choose a concrete broker (IBKR / Tradovate / Rithmic) and implement its
   adapter satisfying `ict_bot.execution.Broker`.
2. Wire a streaming bar feed (websocket or polled HTTP) into `LiveRunner`.
3. Run paper for N sessions and verify per-trade parity with the backtest
   expectation; only then enable live capital.
4. Periodic re-validation: re-run `walk_forward_cme.py` monthly to catch
   regime drift.

## Phase 0 — Definition of done

- [x] Directory tree per `README.md`
- [x] `pyproject.toml` with `ruff` + `mypy --strict` + `pytest` + dependencies pinned
- [x] `.gitignore`, `.env.example`, `.python-version`
- [x] `README.md`, `STRATEGY.md`, `ROADMAP.md`, `docs/architecture.md`, `docs/glossary.md`
- [x] Research PDF + markdown moved to `docs/research/`
- [x] Empty `__init__.py` in every Python package
- [x] `.gitkeep` in `data/`, `reports/`, `logs/`, `checkpoints/`, `docs/concepts/`, `tests/fixtures/`
- [x] `git init` + first commit + push to `https://github.com/dantndev/ict_x_claude.git`

## Phase 1 — Concept catalog (formalization order)

Specs will be authored in this order. Each one needs user sign-off before its implementation is added to `src/`.

1. Swing High / Swing Low (3-bar fractal + N-bar generalization)
2. Market Structure (HH/HL/LH/LL), Break of Structure, Change of Character, Market Structure Shift
3. Displacement (body/range ratio vs ATR)
4. Fair Value Gap — BISI, SIBI, Consequent Encroachment, Balanced Price Range, Volume Imbalance
5. Order Block (bullish/bearish) + Mean Threshold
6. Breaker Block
7. Mitigation Block
8. Rejection Block
9. PD Array hierarchy & invalidation rules
10. Liquidity — Buy-Side, Sell-Side, equal highs/lows, sweep, inducement
11. Dealing Range, Premium/Discount, Equilibrium
12. Optimal Trade Entry (Fibonacci 0.62 / 0.705 / 0.79)
13. Power of Three (accumulation / manipulation / distribution)
14. Killzones, Midnight Open, NY session model
15. **Unicorn Model** (composition spec)

Setups (Phase 4) compose the above; they get their own specs once primitives are locked.
