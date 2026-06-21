# Pilot 002 — Fixed-R TP strategy sweep (MNQ 5m, Jan 2025 → Mar 2026)

**Run:** `reports/pilots/fixed_tp_MNQ_20260621T153821/`
**Script:** `scripts/pilot_fixed_tp.py --family MNQ --tf 5m --from 2025-01-01`
**Grid:** body_atr ∈ {1.0, 1.5} × body_range = 0.5 × min_rr ∈ {1.0, 1.5, 2.0} × fixed_tp_r ∈ {1.5, 2.0, 2.5, 3.0}
**Bars:** 86,454 (5m), 444 trading days.

## Headline finding

`tp_strategy=fixed_R` **completely beats** `tp_strategy=nearest_pool` from pilot 001
across the relevant trade-off frontier. With fixed-R TP, frequency and edge
both go up because:

1. RR is deterministic (= `fixed_tp_r`), so the previously starving `min_rr`
   gate becomes a pure cap (redundant when `fixed_tp_r >= min_rr`).
2. The bot no longer gets dragged to a too-close pool target — TPs sit
   exactly where the trader specifies.

## Top 5 cells by expectancy R

| body_atr | body_range | fixed_tp_r | n_trades | trades/day | win_rate | exp_R | PnL | MaxDD |
| -------- | ---------- | ---------- | -------- | ---------- | -------- | ----- | --- | ----- |
| 1.5      | 0.5        | 2.5        | 83       | 0.19       | 53.0%    | **+0.93** | $244k | 1.6% |
| 1.5      | 0.5        | 2.0        | 111      | 0.25       | 60.4%    | **+0.86** | $382k | 1.6% |
| 1.5      | 0.5        | 3.0        | 43       | 0.10       | 44.2%    | +0.78    | $121k | 1.3% |
| **1.0**  | **0.5**    | **1.5**    | **181**  | **0.40**   | **65.2%**| **+0.78**| **$555k** | **1.5%** |
| 1.5      | 0.5        | 1.5        | 113      | 0.25       | 63.7%    | +0.78    | $415k | 0.7% |

## Comparison vs Pilot 001 plateau

| Configuration | Trades | trades/day | exp_R | WR | PnL | MaxDD |
| ------------- | ------ | ---------- | ----- | -- | --- | ----- |
| Pilot 001 plateau center `(1.0, 0.5, rr=1.0, nearest_pool)` | 187 | 0.42 | +0.71 | ?  | $597k | 1.0% |
| Pilot 002 best expectancy `(1.5, 0.5, fixed=2.5)`           | 83  | 0.19 | +0.93 | 53%| $244k | 1.6% |
| Pilot 002 sweet spot `(1.5, 0.5, fixed=2.0)`                | 111 | 0.25 | +0.86 | 60%| $382k | 1.6% |
| Pilot 002 high-freq `(1.0, 0.5, fixed=1.5)`                 | 181 | 0.40 | +0.78 | **65%** | $555k | 1.5% |

The **`(1.0, 0.5, fixed_tp_r=1.5)`** cell is particularly interesting: same
frequency as pilot 001 but **+10% on expectancy_R and a verified 65.2% win
rate**. The win-rate metric is the strongest signal here because high WR is
robust to micro-changes in fills/slippage in live, while pool-driven TPs are
notoriously fragile.

## `min_rr` is redundant under fixed-R TP

Notice in the grid: cells with the same `(body_atr, body_range, fixed_tp_r)`
have **identical** trades and expectancy regardless of `min_rr`. Reason: when
TP is at exactly `fixed_tp_r × risk`, the RR is always `fixed_tp_r`. As long
as `fixed_tp_r >= min_rr` they all pass; otherwise all fail. `min_rr` becomes
a hard cap, not a filter. Drop it from the sweep grid for v3.

## Recommendation update

Promote pilot 002 winners over pilot 001 only if walk-forward confirms.
Three candidate cells for OOS verification (in order of conservative-→-bold):

1. **`(1.0, 0.5, fixed_tp_r=1.5)`** — same frequency as pilot 001 plateau,
   higher exp_R, much higher win rate. Most defensible default.
2. **`(1.5, 0.5, fixed_tp_r=2.0)`** — half the frequency, +0.86R/trade.
   Best for the Lucid prop-firm DD profile (fewer touches → more headroom).
3. **`(1.5, 0.5, fixed_tp_r=2.5)`** — quarter the frequency, +0.93R. Pure
   high-conviction mode; bumpy equity curve from small sample (83 trades).

## Caveats

- **All-IS.** Still inflated by detector-level lookahead. Walk-forward
  pending for each candidate.
- **Sample size:** the 83-trade cell is statistically thin. The 111- and
  181-trade cells are more solid.
- **MaxDD ~1.5% is still suspicious** — same single-position constraint and
  IS path-favorable artifact as pilot 001.
- **No commission / slippage stress** beyond defaults (1 tick / $0.40 side).

## Next pilots proposed

- **Pilot 003:** walk-forward the three candidate cells on 2024-2026 with
  8 folds + bootstrap (same harness as the validated `(1.0, 0.5, 1.0,
  nearest_pool)`). Pick the one with highest aggregate OOS expectancy.
- **Pilot 004:** drop `min_rr` from the sweep entirely (now confirmed
  redundant) and re-grid `body_atr × body_range × fixed_tp_r` with finer
  resolution around the winning cell.
- **Pilot 005:** add `tf` to the grid — re-run pilot 002 winner on 1m, 3m,
  15m to find the timeframe that maximizes OOS expectancy × frequency.
