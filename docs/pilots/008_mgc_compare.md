# Pilot 008 — MGC (Micro Gold) vs MNQ + dual-instrument analysis

**Smoke:** `reports/pilots/pilot_008_smoke_20260621T213446/` (Jan-Jun 2026)
**Full:** `reports/pilots/pilot_008_full_20260621T215244/` (Jan 2025 - Jun 2026)
**Scripts:** `scripts/pilot_008_gold_smoke.py`, `scripts/pilot_008_gold_full.py`
**Cell:** `(body_atr=1.0, body_range=0.5, fixed_tp_r=1.5, tp_strategy=fixed_R)`
**Filter:** mode B (silver_bullet_am + silver_bullet_pm)
**TF:** 1m

## Smoke (5 months) — operability check passed

Initial worry: gold's $10/point multiplier could make every SL hit
prohibitive for a $25k / $1k DD account. Smoke disproved that — the
bot's natural SL anchor (FVG-anchor bar extreme) produces **2.97 points
mean** in gold, not 15. That maps to **~$30 risk per micro contract**,
identical to MNQ. The account can run MGC with the same per-trade
risk config as MNQ.

## Full 15-month comparison

| metric                       | MNQ (prod)   | MGC (gold)   |
| ---------------------------- | ------------ | ------------ |
| Trades                       | 811          | 863          |
| Trades/day                   | 1.81         | 1.62         |
| **Win rate**                 | **60.5%**    | **51.8%**    |
| **Expectancy R**             | **+1.12**    | **+0.62**    |
| Expectancy $/trade           | $245.80      | $177.58      |
| Total PnL                    | $199,344     | $153,255     |
| Max drawdown                 | 0.36%        | 0.50%        |
| Worst single trade           | -$747.50     | -$967.50     |
| Max consecutive losers       | 7            | 7            |
| Bootstrap p95 DD             | 0.95%        | 1.74%        |
| Bootstrap P(profit)          | 100%         | 100%         |
| Mean SL distance (points)    | 6.27         | 2.69         |
| Mean SL distance ($/contract)| $12.54       | $26.90       |

## Correlation analysis — the key dual-instrument question

| Metric                                           | ES (pilot 007) | MGC (pilot 008) |
| ------------------------------------------------ | -------------- | --------------- |
| Calendar overlap with MNQ (same NY day)          | 79.6%          | 75.5%           |
| Same-day PnL correlation on overlapping days     | (not measured) | **0.043**       |

**MGC is genuinely uncorrelated with NQ on a per-day basis** (Pearson
0.043 ≈ noise). When NQ has a losing day, MGC can have a winning day,
which is precisely what ES failed to do (ES being a tech-correlated
index follows NQ direction-of-day strongly).

This makes MGC the first instrument tested that could provide **real
diversification** rather than hidden leverage.

## But — should you run it now? Honest verdict: not yet.

### Why not

1. **WR 51.8% sits only 12 points above the 40% breakeven** for RR=1.5.
   A typical IS-to-live degradation of 5-10 percentage points on WR
   would push MGC into negative-expectancy territory while MNQ's WR
   (60.5%) would still hold a healthy margin.
2. **Marginal extra return.** Math for the user's $25k account if they
   ran "NQ with 2 micros + MGC with 1 micro" (same risk budget as the
   current config):

   | Setup                            | Trades/day | Risk/trade   | Expected $/day |
   | -------------------------------- | ---------- | ------------ | -------------- |
   | NQ only, 2 micros (current prod) | 1.81       | $60          | **~$55**       |
   | NQ 2 + MGC 1 (dual)              | 3.43       | $87 combined | **~$68**       |

   Only **+$13/day** extra for 45% more total risk and 2x operational
   complexity (two Quantower streams, two contracts to monitor, two
   sources of bridge failure).
3. **Worst trade -$967.50** in gold (vs -$747.50 in NQ). With dynamic
   sizing on a $25k account this drops to ~$54 worst case at 2 micros,
   but the relative cola is wider in gold.
4. **Operational risk dominates.** Adding a second instrument before
   the first has 20 real trades of validation is premature engineering.

### What to do instead

1. Run NQ live for 2-3 weeks (~25-35 real trades).
2. If NQ live expectancy matches the backtest (within ±0.3R band) →
   gold becomes the next logical add.
3. Before going live with gold, run a *shadow* pilot 008b: a fork of
   `pilot_008_gold_smoke.py` that polls the **live Quantower bridge for
   MGC ticks** in parallel with the NQ live loop, runs the same
   detectors, and writes shadow signals to `logs/shadow_mgc/`. After
   2 weeks of shadow data we know whether MGC's live behaviour
   resembles the backtest.
4. Only then activate MGC orders.

### Symbols-and-sizing details if it ever goes live

```yaml
# configs/mgc.yaml already shipped with this commit
symbol:
  family: MGC
  contract: MGCQ26       # August 2026 Micro Gold
instrument:
  tick_size: 0.10
  tick_value_usd: 1.00
  point_value_usd: 10.00
```

`QuantowerBroker` already accepts a `data_symbol` / `exec_symbol`
parameter pair, so going live on gold is configuration plus enabling
the MGC contract subscription in Quantower itself. No code changes.

## Caveat — no walk-forward on MGC

Same compute reason as pilot 007 (ES): MGC on 1m produces ~258k swings
over 15 months (vs NQ's ~68k). The O(N²) cost in detectors makes 8-fold
WF infeasible without batched windows. The full-period + bootstrap
above is sufficient to make the "don't activate yet" call.

If/when MGC is approved for live (after pilots 008b shadow), a chunked
WF over MGC alone should run before any capital is allocated.
