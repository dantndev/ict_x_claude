# 12 — Power of Three (PO3)

> **Status:** spec v1 — pending sign-off
> **Source:** `docs/research/ict_concepts_research.md` § "Fundamentos Lógicos de la Entrega de Precios Interbancaria" (PO3 paragraph)
> **Cross-reference:** [ictindex.io](https://www.ictindex.io/) — query *"power of three", "PO3", "judas swing"*
> **Implements:** `src/ict_bot/signals/setups/po3.py` (Phase 4)
> **Depends on:** [01](./01_swing_points.md), [02](./02_market_structure.md), [10](./10_liquidity.md), [13](./13_sessions_killzones.md)

## 1. Definition

The **Power of Three (PO3)** is ICT's session-level state machine: every meaningful trading session (daily, weekly, sometimes hourly) cycles through three sequential phases driven by the IPDA:

| Phase | Behavior | Algorithmic signature |
| ----- | -------- | --------------------- |
| **Accumulation** | Price ranges in a tight band; institutional positions are being built. | Low directional displacement; ATR low; obi neutral; tight spread. |
| **Manipulation (Judas Swing)** | A counter-bias move that sweeps liquidity *opposite* to the true daily direction. Stop-hunts retail. | A sweep (concept 10) against the expected daily bias, often early in the session. |
| **Distribution** | The true directional expansion toward the targeted liquidity pool. | Displacement leg(s) (concept 03) in the bias direction culminating in a Low-Resistance Liquidity Run (LRLR). |

The bot uses PO3 as a **session bias filter** and a **setup confirmation**: only enter in the direction of the true bias *after* the manipulation leg has completed.

## 2. Notation

| Symbol | Meaning |
| ------ | ------- |
| `S`             | A session window (e.g., NY session 7:00–16:00 NY) |
| `bias(S)`       | Expected directional bias of the session (`BULL` / `BEAR` / `NONE`) |
| `phase(t)`      | Current PO3 phase at bar `t` within `S` |
| `judas(S)`      | The detected manipulation move, if any |
| `mid_open`      | Midnight Open price for filter check (concept 13) |

## 3. Formal definition

### 3.1 Bias source

The session bias is derived from the **HTF state** (concept 02) at the session open:

```
bias(S) = state_HTF(S.start_t)            # BULL, BEAR, or RANGE → NONE
```

When HTF state is RANGE, PO3 is `DISABLED` for that session.

### 3.2 Phase boundaries (intraday)

For a session `S = [t_open, t_close]` and bias `b ∈ {BULL, BEAR}`:

```
PHASE 1 — ACCUMULATION:
    starts at t_open
    ends at the first sweep event against bias direction within S
         OR at t_open + max_accum_bars (config)
         OR at first displacement leg in bias direction (no Judas)

PHASE 2 — MANIPULATION:
    starts at the sweep against bias (the Judas) within S
    ends when an MSS in the bias direction (concept 02) confirms the reversal of the Judas
    judas(S) := this sweep event

PHASE 3 — DISTRIBUTION:
    starts at the MSS that ends Phase 2
    runs until t_close OR an LRLR completes (price reaches the targeted opposite liquidity pool)
```

If no manipulation sweep occurs within `[t_open, t_open + judas_window_bars]`, PO3 is downgraded to `NO_JUDAS` and the session is traded only via standard setups.

### 3.3 Bias check by Midnight Open

A long PO3 distribution entry must be priced **below** `mid_open` at entry time; short below — sorry, above. This is the universal filter from `STRATEGY.md`.

```
PO3_long_entry_allowed   ⇔  entry_price  <  mid_open
PO3_short_entry_allowed  ⇔  entry_price  >  mid_open
```

## 4. Detection (pseudocode)

```text
input:
    bars in session S
    state_htf(t):      function → BULL/BEAR/RANGE (concept 02 on HTF)
    sweeps:             registry (concept 10)
    mss_events:         registry (concept 02)
    mid_open:           price (concept 13)
    config:             { max_accum_bars, judas_window_bars }

bias = state_htf(S.start_t)
if bias == RANGE:
    return PO3State(bias=NONE, phase=DISABLED, judas=None)

phase = ACCUMULATION
judas = None
distribution_start = None

for t in S:
    if phase == ACCUMULATION:
        # Look for manipulation sweep (against bias) or premature displacement
        against = SSL if bias == BULL else BSL
        s = sweep_at_or_before(t, side=against)
        if s and S.start_t <= s.t <= min(S.start_t + config.judas_window_bars, t):
            judas = s
            phase = MANIPULATION
        elif displacement_in_bias_direction(t, bias):
            phase = DISTRIBUTION
            distribution_start = t

    elif phase == MANIPULATION:
        # Wait for MSS in bias direction
        if any(mss.t == t and mss.direction == bias for mss in mss_events):
            phase = DISTRIBUTION
            distribution_start = t

    elif phase == DISTRIBUTION:
        # remain until session end or LRLR completion
        if reached_target_liquidity(t, bias):
            break

# Entry gating
def po3_entry_allowed(price, direction, t, mid_open):
    if phase != DISTRIBUTION: return False
    if direction != bias:     return False
    if direction == BULL and price >= mid_open: return False
    if direction == BEAR and price <= mid_open: return False
    return True
```

## 5. Invalidation

- A PO3 instance is **invalidated** if during Phase 3 the price body-closes back *across* the Judas sweep level — the manipulation was real, the distribution is not yet underway. State reverts to MANIPULATION; engine may re-enter Phase 3 if a new MSS fires later in the session.
- At `S.end_t`, all PO3 state is reset for the next session.

## 6. Confluence rules

- PO3 distribution **+** entry inside an OTE zone of the distribution leg = preferred composition.
- PO3 distribution **+** Unicorn (concept 14) inside the OTE zone = highest-confidence setup of the day.
- PO3 with multiple sweeps in Phase 2 (multi-touch Judas) = stronger; the IPDA collected more liquidity before the move.

## 7. Parameters (configs/default.yaml)

```yaml
po3:
  bias_source_timeframe: "1D"     # state_HTF reference
  max_accum_bars: 60              # max bars in Phase 1 before downgrade
  judas_window_bars: 90           # how far into the session a Judas can still count
  enable_no_judas_mode: true      # allow standard setups when PO3 is downgraded
  apply_midnight_open_filter: true
```

## 8. Test fixtures

- `tests/fixtures/po3/bull_session_clean.csv` — bullish HTF bias, SSL sweep at minute 30, MSS-bull, distribution into BSL → full PO3 sequence detected with correct phase timestamps.
- `tests/fixtures/po3/no_judas_downgraded.csv` — bullish HTF bias, no Judas within window, direct displacement → state `DISTRIBUTION` reached but tagged `no_judas`.
- `tests/fixtures/po3/range_disabled.csv` — HTF state RANGE → PO3 disabled.
- `tests/fixtures/po3/judas_reverses_back.csv` — Phase 3 starts, then body close back across Judas → state reverts to MANIPULATION.

## 9. Open questions

- **(Q12.a)** Bias source — D state vs an explicit "previous day's close vs Midnight Open" rule? **Default v1:** D state from concept 02; expose `bias_source` for ablation.
- **(Q12.b)** LRLR detection — needs its own micro-spec (a fast, low-pullback move toward the opposite extreme). **Default v1:** treat as "reached opposite extreme of dealing range within `K` bars without a counter-displacement". Add v1.1 if backtest shows utility.
- **(Q12.c)** Multiple sessions per day (London + NY): nested PO3 or two independent PO3s? **Default v1:** two independent PO3 instances per day, gated by killzone definitions in concept 13.

## 10. Cross-references

- Bias from [02 — Market Structure](./02_market_structure.md) on HTF.
- Sweeps from [10 — Liquidity](./10_liquidity.md).
- Midnight Open filter from [13 — Sessions/Killzones](./13_sessions_killzones.md).
- Sets the stage for distribution-phase setups; composes with [14 — Unicorn](./14_unicorn_model.md) and Phase-4 setups.
