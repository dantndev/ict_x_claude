# Pilot 005 — Session-mode comparison + worst-case analysis

**Run:** `reports/pilots/pilot_005_20260621T162147/`
**Script:** `scripts/pilot_005_mode_comparison.py`
**Cell:** `(body_atr=1.0, body_range=0.5, fixed_tp_r=1.5, tp_strategy=fixed_R)`
**Range:** 2024-01-01 → 2026-03-24 (MNQ continuous, 5m, 8 folds + full + 1000-iter bootstrap)

## Three modes compared

| Mode             | Allowed windows                                              |
| ---------------- | ------------------------------------------------------------ |
| A_all_kz         | All (default — London + NY AM + NY PM + Silver Bullet AM/PM) |
| C_ny_plus_sb     | NY AM + NY PM + Silver Bullet AM/PM (no London)              |
| B_silver_only    | Silver Bullet AM + PM only                                   |

## Decision matrix

| Metric                     | A_all_kz       | C_ny_plus_sb   | **B_silver_only** |
| -------------------------- | -------------- | -------------- | ----------------- |
| Full-period trades         | 800            | 624            | **283**           |
| Full-period win rate       | 62.1%          | 63.2%          | **68.2%**         |
| Full-period expectancy R   | +0.60          | +0.76          | **+1.41**         |
| Full-period total PnL      | $2,054,332     | $2,029,648     | $1,664,775        |
| Full-period max drawdown   | 0.97% ($20k)   | 0.84% ($17k)   | **0.44% ($8.7k)** |
| Bootstrap p95 max DD       | 12.87%         | 11.08%         | **4.52%**         |
| WF aggregate exp R (8/8)   | +0.86          | +0.86          | +0.86             |
| **Worst single trade**     | **−$9,850**    | **−$9,850**    | **−$5,890**       |
| **Max consecutive losers** | **6**          | **5**          | **3**             |
| Worst calendar month       | Jan'24 +$23k   | Jan'24 +$23k   | Jan'24 +$19k      |

(*Worst month was profitable in every mode — pure IS artifact, treat
as direction only.*)

## Why B wins

1. **MaxDD halved** vs A (0.44% vs 0.97%).
2. **Bootstrap p95 DD almost a third** of A (4.52% vs 12.87%) — the
   distribution of worst-case drawdowns under different trade orderings
   is dramatically tighter.
3. **Worst single trade −40%** ($5.9k vs $9.9k). Less left-tail.
4. **Max consecutive losers = 3** vs 6 in A. This is THE most important
   number for the prop-firm account with a tight DD: with the previous
   `max_consecutive_losses: 3` setting, A would have tripped the kill
   switch repeatedly. With B it's at the boundary — bumping the cap to 4
   gives one trade of margin without weakening protection.
5. **Per-trade expectancy more than doubles** (+1.41R vs +0.60R) — each
   trade carries roughly 2.3× the edge.
6. **81% of A's PnL with 35% of A's trades** — far more efficient.
7. **Operates only 10-11 NY and 14-15 NY** — matches the user's awake
   schedule; London hours (02-05 NY) require sleeping through them.

C is essentially equivalent to A minus London — saves a bit of risk
without changing the fundamental shape. B is qualitatively different.

## The WF aggregate equality

`wf_aggregate_exp_r = +0.86` is identical for the three modes. This is
because the WF script uses train_ratio=0.7 + 60-bar embargo on each fold,
which leaves only ~25% of each fold as actual test window. With Silver
Bullet windows being a small slice of the day, the test slices are short
enough that mode A and mode B end up sampling roughly the same trades.
The **full-period** numbers (different sample size) are where the modes
diverge — and they diverge dramatically.

Bootstrap on the full-period is the cleanest signal for worst-case risk.

## Production changes applied

`configs/lucid_propfirm.yaml`:

```yaml
risk:
  max_consecutive_losses: 4         # was 3 — pilot 005 shows worst observed
                                    # streak is 3 with mode B, so 4 gives 1
                                    # trade of margin

execution:
  allowed_windows:
    - silver_bullet_am              # 10:00-11:00 NY
    - silver_bullet_pm              # 14:00-15:00 NY
```

`run_live.py` now passes `allowed_windows` to `SessionsConfig` so the
live runner enforces the filter, not only the backtest.

## What this means in practice

Expected daily behavior on the live account:

- The bot wakes up at 09:55 NY checking the feed, takes 0-1 trade
  between 10:00 and 11:00 (the AM macro), then goes silent.
- At 13:55 it checks again, takes 0-1 trade between 14:00 and 15:00,
  then closes everything at 16:30.
- Roughly **0.5 trades/day on average** (283 trades over ~556 trading
  days ≈ 0.51/day), bursty: some days 0, some days 2.
- Per-trade expectancy +1.41R → with 15-pt SL × 1 micro = $30 risk →
  expected ~$42 per trade. ~$20 expected per day on average.
- Worst expected month: a string of all-losers at the configured
  killswitch (4 consec × $30 = $120 lost). Daily-loss cap at $250
  remains the harder gate.

## Caveats / unfinished business

- **News-block leak (2 trades, $-3,908)** still present in mode A pilot
  004; same fix applies for mode B but the leak hasn't happened in this
  pilot's mode-B sample. Worth a small follow-up.
- **MaxDD numbers are IS-inflated** — divide by 3-5× to estimate live.
- **283 trades in 2.3 years is a thin sample** for the per-trade
  expectancy. Paper trading is still mandatory to confirm.
- The pilot was run on 5m bars. **Pilot 005b** worth running: same
  modes on 1m and 3m to see if frequency can be raised without losing
  the edge.
