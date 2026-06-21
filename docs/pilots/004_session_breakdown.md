# Pilot 004 — Winner re-WF with limits fix + per-killzone breakdown

**Run:** `reports/pilots/pilot_004_20260621T160920/`
**Script:** `scripts/pilot_004_session_breakdown.py`
**Cell:** `(body_atr=1.0, body_range=0.5, fixed_tp_r=1.5, tp_strategy=fixed_R)`
**Range:** 2024-01-01 → 2026-03-24 (MNQ continuous, 5m)

## Clean numbers after the limits-streak bugfix

| Metric | Value |
| ------ | ----- |
| WF aggregate exp R (8 folds) | **+0.86** |
| WF aggregate PnL OOS         | **$401,282** |
| WF folds positive            | 8 / 8 |
| Full-period trades           | 800 |
| Full-period win rate         | 62.1% |
| Full-period expectancy       | $2,567.92 / +0.61 R |
| Full-period total PnL        | $2,054,332 |
| Full-period max drawdown     | $20,212 (0.97%) |
| Bootstrap 1000 prob. profit  | **100.0%** |
| Bootstrap p95 max DD         | 12.87% |

The bugfix to `LimitsState.reset_for_day` (now also clears
`consecutive_losses` + `locked_for_streak`) raised the full-period trade
count from a broken 4-6 to a realistic 800. The aggregate WF numbers
match pilot 003.

## Per-killzone breakdown — the surprise

| session              | trades | WR  | exp R | total PnL    | % trades | % PnL  |
| -------------------- | ------ | --- | ----- | ------------ | -------- | ------ |
| **silver_bullet_am** | 191    | 64% | +1.30 | **$1,157,118** | 23.9%  | **56.3%** |
| **silver_bullet_pm** | 119    | 71% | +1.48 | **$624,082**   | 14.9%  | **30.4%** |
| ny_am_kz             | 225    | 60% | +0.21 | $192,620     | 28.1%    | 9.4%   |
| london_kz            | 177    | 59% | +0.09 | $45,482      | 22.1%    | 2.2%   |
| ny_pm_kz             | 81     | 56% | **-0.06** | $30,800   | 10.1%    | 1.5%   |
| idle                 | 5      | 80% | +0.37 | $8,138       | 0.6%     | 0.4%   |
| news_block           | 2      | 50% | -1.10 | -$3,908      | 0.2%     | -0.2%  |

(`ny_pm_kz` numbers are for the **net** window — Silver Bullet PM trades at
14:00-15:00 get classified as `silver_bullet_pm` first, so what's left of
NY PM is 13:30-14:00 + 15:00-16:00, ~1.5 hours.)

## What this means

**87% of all PnL comes from 2 hours per day** — Silver Bullet AM (10-11 NY)
and Silver Bullet PM (14-15 NY), the canonical ICT macros. London adds
near-zero, and NY PM "net" (without SB PM) is **slightly losing**.

The user does not stay awake for London (sleep), so dropping it is free.
The only real decision is whether to drop NY PM net too (Opción B) or
keep it as a small filter on top (Opción C).

## Caveat

This breakdown is on the IS full-period run. The dollar magnitudes are
inflated by detector-level lookahead. The **direction** of the effect
(SB >> others) is robust because it's a relative comparison within the
same backtest pass, but absolute PnL is not directly transferable to live.

Pilot 005 walk-forwards each session-filter mode separately and adds
worst-fold / worst-month / max-consecutive-losers so the user can decide
B vs C on actual drawdown realism, not IS magnitudes.

## news_block leak

2 trades classified as `news_block` (the 08:30-08:35 window) entered
the portfolio. They should have been pre-flighted out by
`new_entries_allowed`. To investigate: the gate fires on the bar-close
timestamp, but a setup could have been *detected* before 08:30 with the
entry bar landing inside 08:30-08:35. Not material (-$3,908 on $2M PnL)
but worth a small follow-up fix.
