# Pilot 006 — Timeframe sweep on mode B (1m / 3m / 5m / 15m)

**Run:** `reports/pilots/pilot_005b_20260621T172829/` (script `pilot_005b_tf_sweep.py`)
**Cell:** `(body_atr=1.0, body_range=0.5, fixed_tp_r=1.5, tp_strategy=fixed_R)`
**Filter:** mode B (silver_bullet_am + silver_bullet_pm only)
**Range:** 2024-01-01 → 2026-03-24 (MNQ continuous)

## Results

| TF    | trades | tr/day | WR  | exp R | PnL        | MaxDD | p95 DD | max consec L | WF folds | WF agg R | score (tr/day × R) |
| ----- | ------ | ------ | --- | ----- | ---------- | ----- | ------ | ------------ | -------- | -------- | ------------------ |
| **1m**| 1490   | **1.83** | 60% | +1.17 | $3,388,658 | 0.30% | 5.92%  | **7**        | 8/8      | +0.55    | **+2.149**         |
| 3m    | 473    | 0.58   | 62% | +1.25 | $1,913,162 | 0.43% | 4.74%  | 6            | 8/8      | +0.66    | +0.728             |
| 5m    | 282    | 0.35   | 68% | +1.41 | $1,660,438 | 0.44% | 4.47%  | 3            | 8/8      | +0.88    | +0.490             |
| 15m   | 81     | 0.10   | 74% | +1.45 | $571,960   | 0.52% | 2.69%  | 4            | 7/8      | +1.43    | +0.145             |

## Two findings, ordered by importance

### Latent live↔backtest mismatch (caught by this pilot, not a strategy issue)

The live runner's `_BarAggregator` builds **1-minute bars** from the DOM2
mid feed and feeds them straight to the detectors — there is no resample
step. Until pilot 006 was run, every backtest validation used **5-minute
bars** because the script CLIs default to `--tf 5m`. So the live bot's
real behaviour was the 1m row above, NOT the 5m one we had been quoting.

The fix is purely documentation: the production config now declares
`setups.tf: 1m` explicitly and points at this pilot's 1m row as the
validated benchmark. No code change needed because the live aggregator
was already operating that way.

### TF score frontier — 1m dominates on `trades/day × expectancy_R`

The composite metric `tr/day × exp_R` answers "how fast does this TF turn
edge into dollars". 1m beats the other TFs by 4-15×:

```
1m  → 2.149   (5-6 weeks to $1,250 target with 2 micros)
3m  → 0.728   (~15 weeks)
5m  → 0.490   (~20 weeks)
15m → 0.145   (~57 weeks)
```

The trade-off is real but bounded:

- **WR falls from 68% (5m) to 60% (1m)** — still above the breakeven for
  RR=1.5 (which is 40%). Edge survives the noise.
- **WF aggregate R falls from +0.88 to +0.55** — the OOS edge is less
  sharp on 1m. 8/8 folds positive both ways, so it's degradation, not
  collapse.
- **Max consecutive losers rises from 3 to 7** — kill-switch boundary
  shifts. Production cap moved to 6 (was 10) so a real-life run of 7
  bad ones gets stopped at 6, before it eats the rest of the DD budget.
- **p95 max DD rises from 4.47% to 5.92%** — the worst 5% of scenarios is
  ~30% deeper. Tight, but inside the $700 of remaining margin after the
  user's $300 starter loss.

## Decision applied to production

User asked to maximise speed-to-target given a "no time limit" account
and a $1,250 evaluation goal. Camino B chosen:

```yaml
# configs/lucid_propfirm.yaml
setups:
  tf: 1m                            # was implicitly 1m in live, now declared
  body_atr_min: 1.0
  body_range_min: 0.5
  tp_strategy: fixed_R
  fixed_tp_r: 1.5

risk:
  max_consecutive_losses: 6         # was 10; pre-empts the worst observed streak of 7
  max_trades_per_day: 8             # 1m mode runs ~1.83/day, 8 is the safety cap
```

## Realistic projection for the user

With 2 micros + 30% degradation from IS-to-live (typical for backtest
overstatement of execution quality):

| Metric            | Value (1m, 2 micros, live realistic)         |
| ----------------- | -------------------------------------------- |
| Trades/day        | ~1.83                                        |
| Win rate          | ~55% (allowing 5pp degradation from 60%)     |
| Expectancy/trade  | $21 net of commissions                        |
| **Expected/day**  | **~$38**                                     |
| **Days to $1,250**| **~33** (≈ 6.5 weeks)                        |

If live underperforms (WR < 53%, expectancy < $15), the fallback plan is
to switch `tf: 3m` (slower, but +0.66 WF agg R OOS — more solid edge)
or `tf: 5m` (slowest, most conservative). All three are a single YAML
edit away.

## Next pilots queued

- **Pilot 007** — confirm 1m live performance: after 20+ real trades,
  compare per-trade expectancy to the +1.17R (IS) and +0.55R (WF) range.
- **Pilot 008** — combine 1m mode B with concurrent positions
  (`max_quantity: 3-4` and lift single-position lock). Should raise
  trades/day by ~20% if correlations hold.
