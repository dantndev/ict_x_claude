# Pilot 001 — Threshold sensitivity sweep (MNQ 5m, Jan 2025 → Mar 2026)

**Run:** `reports/pilots/sensitivity_MNQ_20260621T152133/`
**Script:** `scripts/pilot_sensitivity_sweep.py --family MNQ --tf 5m --from 2025-01-01 --grid default`
**Bars:** 86,454 (5m), 444 trading days.
**Note:** all-IS metrics (no walk-forward). Use for parameter selection only; OOS verification via `walk_forward_cme.py`.

## Headline finding

`min_rr ≥ 1.5` kills the strategy under the current `tp_strategy=nearest_opposite_pool`. All 18 grid cells with `min_rr ∈ {1.5, 2.0}` produced **0 trades** because the pool registry is dense — there is almost always a pool between 1R and 1.5R from entry, which passes the `min_tp_distance_in_risks=1.0` floor but fails the RR floor.

Only the 9 cells with `min_rr=1.0` are tradable.

## Top 5 cells by expectancy R

| body_atr_min | body_range_min | min_rr | n_trades | trades/day | expectancy_R | total_pnl_usd | max_dd_pct |
| ------------ | -------------- | ------ | -------- | ---------- | ------------ | ------------- | ---------- |
| 1.5          | 0.6            | 1.0    | 117      | 0.26       | **+0.792**   | $438,478      | 0.6%       |
| 1.5          | 0.4            | 1.0    | 111      | 0.25       | +0.783       | $391,228      | 1.1%       |
| 1.5          | 0.5            | 1.0    | 111      | 0.25       | +0.783       | $391,228      | 1.1%       |
| 0.8          | 0.5            | 1.0    | 143      | 0.32       | +0.769       | $527,473      | 1.0%       |
| 0.8          | 0.4            | 1.0    | 144      | 0.32       | +0.762       | $529,245      | 1.0%       |

## Robust plateau (adjacent cells with similar expectancy)

The three cells at `body_atr=1.0` form a stable plateau, not a single overfit peak:

| body_atr | body_range | min_rr | trades | exp_R | PnL |
| -------- | ---------- | ------ | ------ | ----- | --- |
| 1.0      | 0.4        | 1.0    | 188    | +0.711| $600,865 |
| 1.0      | 0.5        | 1.0    | 187    | +0.707| $597,027 |
| 1.0      | 0.6        | 1.0    | 207    | +0.651| $625,902 |

Plateaus are preferred over peaks for production parameters because they are
less likely to be artifacts of overfitting.

## Frequency vs quality trade-off

| Preference | Cell | trades/day | exp_R |
| ---------- | ---- | ---------- | ----- |
| **Selectivity** (highest exp_R)         | `(1.5, 0.6, 1.0)` | 0.26 | +0.79 |
| **Balanced** (plateau center, recommended) | `(1.0, 0.5, 1.0)` | 0.42 | +0.71 |
| **Frequency** (still positive edge)    | `(0.8, 0.6, 1.0)` | 0.66 | +0.65 |

## Recommendation for `configs/lucid_propfirm.yaml`

Replace the canonical strict thresholds with the plateau-center values:

```yaml
setups:
  body_atr_min: 1.0
  body_range_min: 0.5
  min_rr: 1.0
```

Expected IS effect on the 15-month sample: ~187 trades (~0.42/day), expectancy
+0.71 R/trade, MaxDD ~1%. With $30 SL per micro (1 contract × 15 pt × $2/pt),
~3 stops in a row ≈ $90 — well under the $250 daily-loss limit.

## Caveats

- **All-IS.** Numbers are inflated by detector-level lookahead (invalidation
  scans full future bars). Run `walk_forward_cme.py` with the recommended
  cell before believing them.
- **No commissions/slippage realism check beyond defaults.** Backtest uses
  1-tick slippage and $0.40/side. NQ fast tape can be 2-3 ticks.
- **MaxDD <1.1% is suspicious.** Likely an artifact of single-position
  constraint + favorable IS path.

## Next pilot proposed

`min_rr ≥ 1.5` only fails because TP is anchored to a pool. A natural follow-up
pilot:

- **`tp_strategy=fixed_2R`** (or `fixed_3R`): TP at exactly N×risk, ignore the
  pool registry for target selection.
- Re-run the grid with `min_rr` extended to `(1.0, 1.5, 2.0, 2.5)` to find
  whether higher RR + fixed-R TP beats the current plateau.

If that pilot shows a higher OOS expectancy than `(1.0, 0.5, 1.0)`, promote it.
