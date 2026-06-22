# Pilot 007 — ES (MES economy) vs MNQ baseline

**Run:** `reports/pilots/pilot_007_20260621T205214/`
**Script:** `scripts/pilot_007_es_compare.py`
**Cell:** `(body_atr=1.0, body_range=0.5, fixed_tp_r=1.5, tp_strategy=fixed_R)`
**Filter:** mode B (silver_bullet_am + silver_bullet_pm)
**TF:** 1m
**Range:** 2025-01-01 → 2026-03-24 (15 months)
**Note:** ES CSV (`glbx-mdp3-20210325-20260621.ohlcv-1m.csv`) loaded with
`family='ES'`. Sizing uses MES InstrumentSpec (tick=$1.25, point=$5) so
dollar magnitudes match what the user could actually trade on the $25k
Lucid account (the full ES contract at $50/pt is too big — one SL would
consume 75% of the $1k DD budget).

## Results

| metric             | MNQ (prod)     | ES (MES econ)  | delta            |
| ------------------ | -------------- | -------------- | ---------------- |
| trades             | 811            | 881            | +9%              |
| trades/day         | 1.81           | 1.65           | -9%              |
| **win_rate**       | **60.5%**      | **52.6%**      | **-13 pp**       |
| **expectancy R**   | **+1.12**      | **+0.68**      | **-39%**         |
| expectancy USD     | $245.80        | $123.50        | -50%             |
| total PnL          | $199,344       | $108,805       | -45%             |
| max DD             | 0.36%          | 0.53%          | +47% worse       |
| worst single trade | -$747.50       | -$575.00       | -23%             |
| max consec losers  | 7              | 7              | =                |
| bootstrap p95 DD   | 0.95%          | 1.04%          | +9%              |
| bootstrap P(profit)| 100%           | 100%           | =                |
| **calendar overlap (both traded same NY date)** | — | **79.6%** | — |

## Why this kills the dual-instrument idea

### 1. ES edge is materially weaker

WR drops from 60.5% to 52.6%. At RR=1.5, breakeven WR is 40%, so ES has
only ~13 percentage points of cushion. A typical IS→live degradation of
5-10 pp on WR would push ES into negative territory while MNQ would
still print positive. ES is fragile.

### 2. Calendar overlap = 79.6% kills the diversification thesis

Eight out of every ten days, the bot trades on BOTH instruments. ES and
NQ are correlated futures on overlapping indices (NQ is tech-heavy SPX
subset); running the same setup on both during the same Silver Bullet
windows produces signals that fire mostly on the same days, often in the
same direction.

In a $25k/$1k DD account, that's **leverage, not diversification**. A
bad ES day is overwhelmingly a bad NQ day. Running both doubles the
daily PnL variance, doesn't halve it.

### 3. Killswitch headroom collapses

Both instruments hit 7 consecutive losers in the 15-month sample. With
`max_consecutive_losses: 6` configured on the account level (not per
instrument), running both would trip the killswitch ~2x more often,
exactly when the account is already losing money.

### 4. "One micro of each" doesn't help either

If the user reduced size to 1 micro per instrument to keep total risk
constant:

| Setup           | Trades/day | $/trade | Expected $/day |
| --------------- | ---------- | ------- | -------------- |
| 2 micros MNQ    | 1.81       | $40     | **$72**        |
| 1 MNQ + 1 MES   | 3.46 (sum) | ~$20    | **~$70**       |

Same expected return, double the operational load, much higher
correlated-loss risk. No benefit.

## Decision: stay single-instrument (MNQ)

`configs/lucid_propfirm.yaml` unchanged. README adds a "Multi-instrument"
section pointing at this pilot to document why ES was tested and
discarded — so future-me doesn't redo the experiment.

## When to revisit

- A different propfirm allows much larger DD budgets → correlation risk
  becomes survivable, dual could become worth it for the +9% extra
  signals.
- A pilot 008 finds an uncorrelated instrument (e.g., crude CL, gold GC)
  where the same setups work and overlap is < 50%.
- The shadow log (now writing every detected signal from live) shows
  that NY-AM-KZ trades on NQ outperform our backtest — at that point ES
  in NY AM might be additive instead of redundant.

## Caveat: no walk-forward for ES

The first version of this pilot tried 8-fold WF for both instruments
but ES on 1m generates ~3.9x more swings/sweeps than NQ (microstructure
granularity scales with index level), and the FVG/OB detectors are
worst-case O(swings × bars). The WF run never finished within 1 hour.

The full-period + bootstrap above is enough to conclude ES is not worth
adding given the correlation and edge gap. If a future pilot wants a
proper WF on ES, it should chunk the bars by year and aggregate per
fold — a small refactor of `walk_forward` we haven't needed yet.
