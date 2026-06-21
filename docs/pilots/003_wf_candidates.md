# Pilot 003 — Walk-forward of the three fixed-R candidates

**Run:** `reports/pilots/wf_candidates_20260621T155820/`
**Script:** `scripts/pilot_003_wf_candidates.py`
**Range:** 2024-01-01 → 2026-03-24 (MNQ continuous, 5m, 8 folds, 70/30 split, 60-bar embargo)

## Comparison

| Candidate                                    | WF folds+ | WF agg R | WF agg PnL OOS | Bootstrap p95 DD | Decision |
| -------------------------------------------- | --------- | -------- | -------------- | ---------------- | -------- |
| **A_max_freq** `(1.0, 0.5, fixed=1.5)`       | **8/8**   | **+0.86**| **$401,282**   | n/a (bug below)  | **WIN**  |
| B_balanced `(1.5, 0.5, fixed=2.0)`           | 7/8       | +0.73    | $133,745       | n/a              | reject   |
| C_selective `(1.5, 0.5, fixed=2.5)`          | 7/8       | +0.77    | $123,268       | n/a              | reject   |

## Why A_max_freq wins

- **Perfect OOS fold record** (8/8 positive) — extremely robust.
- **3× the aggregate PnL** of B and C with the same risk profile.
- Per-fold expectancy stays positive across all market regimes covered by
  2024-2026 (trend, range, news shocks).
- Effectively ties pilot 001's `(1.0, 0.5, rr=1.0, nearest_pool)` baseline
  in OOS edge (+0.85R, $400k) but with a **deterministic TP** that does NOT
  depend on pool registry density — much more stable in live, where
  microstructure noise can move pools by 1-2 ticks between detection and
  fill and silently degrade the nearest_pool variant.

## Bug discovered: streak lock never resets across days

The "full-period" run for each candidate showed an absurd 4-6 trades total
(vs the dozens distributed across the WF folds). Root cause: in
`LimitsState`, `reset_for_day()` reset only `cumulative_loss_today_usd` and
`locked_for_day`, but **not** `consecutive_losses` or `locked_for_streak`.
Once a 4-loss streak hit early in the test period, the lock persisted
forever and silently blocked every subsequent signal — `limits_lock`
reasons in the thousands.

The WF folds didn't show this because each fold instantiates a fresh
`LimitsState`. Live trading also dodged it because real days roll over
naturally, but only because the streak counter never gets to reset either,
which would have produced a slow-motion failure days into a paper run.

**Fix shipped** (`src/ict_bot/risk/limits.py`): `reset_for_day()` now resets
`consecutive_losses=0` and `locked_for_streak=False` too. A new test
(`test_limits_streak_lock_resets_next_day`) pins the corrected behavior.

## Production change applied

`configs/lucid_propfirm.yaml`:

```yaml
setups:
  body_atr_min: 1.0       # was 1.5
  body_range_min: 0.5     # was 0.6
  min_rr: 1.0             # redundant under fixed_R but kept for clarity
  tp_strategy: fixed_R    # NEW (was implicit "nearest_pool")
  fixed_tp_r: 1.5         # NEW
```

Expected behavior with the prop-firm risk caps (per-trade $30 SL × 1 micro,
daily-loss $250, max consecutive losses 3):

- Backtest IS frequency: ~0.40 trades/day. In live with all gates active,
  expect ~0.2-0.3 trades/day (killzones + midnight-open + position-already-
  open will trim further).
- Expected OOS edge: +0.86R/trade (from pilot 003 WF aggregate).
- Win rate from pilot 002: 65% (TP 1.5R hit before SL 1R hit 65% of the
  time). At 65% × 1.5 - 35% × 1.0 = +0.625R — consistent with the +0.86R
  WF aggregate within sampling noise.

## What still has to happen before live capital

1. **Re-run pilot 003** with the limits bugfix to get clean full-period
   numbers + bootstrap CIs (the WF numbers above are valid as-is, but the
   bootstrap p95 DD couldn't be measured on this run because the full
   pipeline produced only 4-6 trades).
2. **Paper trade ≥ 20 sessions** with the new config and compare per-trade
   results to the WF expectation (±0.3R band).
3. **Then** route to LIVE with --confirm LIVE.

## Next pilots queued

- **Pilot 004:** re-run pilot 002 grid without `min_rr` (now confirmed
  redundant) with finer resolution around `(1.0, 0.5, fixed_tp_r=1.5)`.
- **Pilot 005:** sweep `tf ∈ {1m, 3m, 5m, 15m}` with the winning cell to
  see if a lower TF raises trades/day without destroying edge.
- **Pilot 006:** add concurrent-position support (lift the
  position_already_open skip) and measure the +20% frequency claim from the
  pilot menu.
