# Roadmap — `ict_x_claude`

Ten phases. Each phase has an explicit definition of done; no phase advances without its predecessor.

| # | Phase | Done when... | Status |
| - | ----- | ------------ | ------ |
| 0 | **Bootstrap** — Repo scaffolding, configs, tooling, first commit | All directories, `pyproject.toml`, `.gitignore`, READMEs exist. Repo pushed to GitHub private. `pytest` runs (no tests yet). | ✅ in progress |
| 1 | **Concept formalization** — One `docs/concepts/<concept>.md` per ICT primitive, with definition → math → detection pseudocode → invalidation → tests fixtures. User sign-off per concept. | All concepts in the V1 catalog have an approved spec. No code in `src/signals/` yet. | ⏳ next |
| 2 | **Data layer** — `data/` module: loaders for L2 CSVs and HTTP OHLCV, validator (gaps/dupes/tz), resampler 1m → 3m/5m/15m/1H/4H/D, unified `Bars` and `Ticks` models. | Loading 3 months of OHLCV + L2 in under 5s; 100% unit coverage of resampler edge cases. | |
| 3 | **Detectors** — Pure implementations of formalized concepts in `structure/`, `signals/imbalance/`, `signals/blocks/`, `signals/liquidity/`, `signals/ranges/`, `sessions/`. | Each detector passes its concept fixture; coverage ≥ 90%. | |
| 4 | **Setups** — Composition of detectors into the V1 setup catalog (Unicorn, MSS+FVG, OB+OTE, Silver Bullet, PO3). | Each setup produces a list of `Signal` objects with entry, SL, TP, confidence, audit trail. | |
| 5 | **Backtest engine** — Event-driven, NQ-aware (tick size 0.25, $20/point), commissions, slippage, SL/TP, session hard-flatten at 16:30, position sizing from `risk/`. | One full backtest of one setup runs on 3 months of data, output: trades CSV + equity parquet + JSON summary. | |
| 6 | **Reporting** — Equity curve, drawdown, Sharpe/Sortino, profit factor, expectancy, R-distribution, per-session/killzone breakdown, day×hour heatmap. HTML report. | One-click report from a backtest run. | |
| 7 | **Robustness** — Walk-forward with embargo, Monte Carlo bootstrap of equity, regime breakdown (trend/range/news days), parameter sensitivity. | Each setup carries a "robustness report" alongside its backtest. | |
| 8 | **ML confirmation (optional)** — Train a *filter* on L2 features (`fp_delta`, `delta_acceleration`, `obi_top10`, `spread_compression`) over rule-based entries. Compare PnL with/without filter. Discard the layer if no edge. | Decision recorded in `docs/concepts/ml_confirmation.md`. | |
| 9 | **Production** — Broker adapter (decide: IBKR / Tradovate / Rithmic), paper-trading runner, structured logs, kill switch, daily loss circuit breaker. Live only after N paper-trading sessions match backtest expectations. | Paper-trading runs unattended for 5 sessions without divergence > 1R from backtest expectation. | |

---

## Phase 0 — Definition of done (current)

- [x] Directory tree per `README.md`
- [x] `pyproject.toml` with `ruff` + `mypy --strict` + `pytest` + dependencies pinned
- [x] `.gitignore`, `.env.example`, `.python-version`
- [x] `README.md`, `STRATEGY.md`, `ROADMAP.md`, `docs/architecture.md`, `docs/glossary.md`
- [x] Research PDF + markdown moved to `docs/research/`
- [x] Empty `__init__.py` in every Python package
- [x] `.gitkeep` in `data/`, `reports/`, `logs/`, `checkpoints/`, `docs/concepts/`, `tests/fixtures/`
- [ ] `git init` + first commit + push to `https://github.com/dantndev/ict_x_claude.git`

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
