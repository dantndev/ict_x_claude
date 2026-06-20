# Architecture

## Module dependency graph (intended)

```
                  ┌─────────────┐
                  │   config    │  (pydantic settings, YAML loader)
                  └──────┬──────┘
                         │
        ┌────────────────┴────────────────┐
        │                                 │
        ▼                                 ▼
   ┌─────────┐                      ┌──────────┐
   │  data   │◄─── HTTP / CSV ──────│  utils   │  (tz, logging, helpers)
   └────┬────┘                      └──────────┘
        │  Bars, Ticks
        ▼
   ┌─────────┐
   │structure│  swing, BoS, ChoCH, MSS, displacement
   └────┬────┘
        │  StructureEvents
        ▼
   ┌─────────────────────────────────────────────┐
   │                  signals                    │
   │  imbalance ─ blocks ─ liquidity ─ ranges    │
   │              ▼ composition ▼                │
   │                  setups                     │
   └────┬────────────────────────────────────────┘
        │  Signal (entry, SL, TP, audit)
        ▼
   ┌─────────┐        ┌──────────┐
   │  risk   │───────▶│ backtest │──▶ reporting
   └─────────┘        └──────────┘
                            │
                            ▼
                       ┌─────────┐
                       │execution│  paper / live (Phase 9)
                       └─────────┘
```

## Boundaries (hard rules)

- **`data/` is the only module that touches I/O for market data.** Everything downstream consumes `Bars` and `Ticks` Pydantic/struct models — never raw CSVs or HTTP responses.
- **`structure/` and `signals/` are pure.** No I/O, no state, no time clock. A detector is a function of `Bars` → `Events`. This is what makes them unit-testable and replayable.
- **`backtest/` is the only module that knows about time advancing bar-by-bar.** Live execution will reuse the same engine wired to a streaming source.
- **`risk/` decides position size and trade gating.** Setups never decide their own sizes.
- **`execution/` is the only module that talks to brokers.** Paper mode is a broker adapter, not a special case scattered through the engine.

## Configuration

All tunable values live in `configs/*.yaml` and are loaded through pydantic models in `config/`. A code change should never be required to:

- Change tick size, contract multiplier, commission, slippage
- Adjust killzone boundaries or session times
- Tune detector thresholds (ATR multipliers, lookback lengths, Fibonacci levels)
- Switch data sources (CSV path, HTTP URL)
- Cap per-trade risk %, daily loss, max trades/day

## Time

`America/New_York` is the canonical timezone. The data layer converts every timestamp on ingest. Downstream modules assume NY time. UTC is preserved on `Ticks` for auditing only.

## Logging

`structlog` JSON output to `logs/`. Each backtest run writes:

- `logs/runs/<run_id>/events.jsonl` — every Signal, every fill, every risk decision
- `logs/runs/<run_id>/summary.json` — backtest metadata + final metrics

## Testing strategy

| Layer | Test kind | Location |
| ----- | --------- | -------- |
| Concepts (FVG, OB, MSS, ...) | Pinned fixtures: synthetic candles where the answer is known | `tests/signals/`, `tests/structure/` |
| Data layer | Property tests (resampler, validator) using `hypothesis` | `tests/data/` |
| Backtest | Golden-output snapshot tests on a small fixture | `tests/backtest/` |
| Integration | Live data load from real localhost + CSV (marked `integration`) | `tests/` (gated by marker) |
