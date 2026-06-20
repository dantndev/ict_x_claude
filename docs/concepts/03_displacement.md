# 03 — Displacement

> **Status:** spec v1 — pending sign-off
> **Source:** `docs/research/ict_concepts_research.md` § "Fase de Desplazamiento"
> **Cross-reference:** [ictindex.io](https://www.ictindex.io/) — query *"displacement"*
> **Implements:** `src/ict_bot/structure/displacement.py` (Phase 3)
> **Depends on:** —
> **Depended on by:** 02 (MSS), 04 (FVG validation), 05 (OB validation), 06 (Breaker), 14

## 1. Definition

**Displacement** is a violent directional move characterized by candles with large bodies relative to both their own range and recent volatility. ICT treats displacement as the *fingerprint* of institutional participation — the algorithmic injection of liquidity that causes structure breaks and leaves Fair Value Gaps.

For the bot, displacement is a **per-bar boolean classifier** plus an aggregate "displacement leg" detector that fuses runs of displacement bars into a single directional event.

## 2. Notation

| Symbol | Meaning |
| ------ | ------- |
| `O_t, H_t, L_t, C_t` | Open, high, low, close at bar `t` |
| `body_t = |C_t - O_t|` | Absolute body size |
| `range_t = H_t - L_t` | Total candle range |
| `ATR_n_t` | Average True Range over the prior `n` bars (Wilder smoothing, excludes `t`) |
| `D_t` | Displacement boolean at bar `t` |

## 3. Formal definition

`D_t = true` iff **all** of the following hold:

1. **Body dominance** — body is a majority of the candle's range:
   ```
   body_t / range_t   ≥   k_br        (default k_br = 0.6)
   ```
2. **Volatility blowout** — body exceeds a multiple of recent ATR:
   ```
   body_t   ≥   k_atr × ATR_n_t        (default k_atr = 1.5, n = 14)
   ```
3. **Direction is unambiguous** — close is on the extreme side:
   ```
   if C_t > O_t:  (H_t - C_t) ≤ k_wick × body_t       (default k_wick = 0.35)
   if C_t < O_t:  (C_t - L_t) ≤ k_wick × body_t
   ```
   (No tail more than 35% of the body.)

Direction of displacement at `t`:

```
dir_t = BULL   if  C_t > O_t  and  D_t
dir_t = BEAR   if  C_t < O_t  and  D_t
dir_t = NONE   otherwise
```

### 3.1 Displacement leg

A **displacement leg** is a maximal contiguous run of bars where `dir_t ∈ {BULL}` (or `{BEAR}`) with no more than `gap_max` bars of `NONE` interrupting (default `gap_max = 1` to allow a single small congestion bar).

The leg's price range is `[min Low_t, max High_t]` over the run. The leg's *direction* equals the constituent bars' direction.

## 4. Detection (pseudocode)

```text
input:
    bars: ordered list of Bar
    config: { k_br, k_atr, n_atr, k_wick, gap_max }

# Per-bar pass
ATR = wilder_atr(bars, n_atr)        # array of length len(bars)
displacement = [None] * len(bars)
for t in n_atr .. len(bars)-1:
    body = abs(bars[t].close - bars[t].open)
    rng  = bars[t].high - bars[t].low
    if rng == 0: continue
    if body / rng < k_br: continue
    if body < k_atr * ATR[t]: continue
    top_wick = bars[t].high - max(bars[t].open, bars[t].close)
    bot_wick = min(bars[t].open, bars[t].close) - bars[t].low
    if bars[t].close > bars[t].open:
        if top_wick > k_wick * body: continue
        displacement[t] = BULL
    elif bars[t].close < bars[t].open:
        if bot_wick > k_wick * body: continue
        displacement[t] = BEAR

# Leg aggregation
legs = []
i = 0
while i < len(bars):
    if displacement[i] in {BULL, BEAR}:
        d = displacement[i]
        j = i
        gap = 0
        end = i
        while j < len(bars):
            if displacement[j] == d:
                end = j
                gap = 0
            elif displacement[j] is None:
                gap += 1
                if gap > config.gap_max: break
            else:
                break
            j += 1
        legs.append(Leg(direction=d, start=i, end=end))
        i = end + 1
    else:
        i += 1

return displacement, legs
```

## 5. Invalidation

A per-bar displacement does not get invalidated — it is a property of the bar at close time.

A **displacement leg** is considered *exhausted* (and no longer eligible to validate a fresh MSS/OB) once one of:

- A counter-direction displacement bar closes inside the leg's range.
- The price retraces past the leg's 50% (the leg's "consequent encroachment") with a body close in the opposite direction.

The engine keeps a registry of active legs and prunes them under either condition.

## 6. Confluence rules

- Displacement is **required** by:
  - MSS (concept 02)
  - Valid Order Block (concept 05) — only OBs preceded by displacement count
  - Valid Breaker (concept 06)
- Displacement *should produce* an FVG (concept 04). A displacement leg that does **not** leave an FVG is downgraded to "weak displacement" — eligible for BoS but not MSS.
- L2 confirmation (Phase 8): a displacement leg with `delta_acceleration` in the matching direction during the leg's bars is `confirmed`; otherwise tagged `unconfirmed`.

## 7. Parameters (configs/default.yaml)

```yaml
structure:
  displacement:
    atr_lookback: 14
    body_range_min: 0.6   # k_br
    body_atr_min: 1.5     # k_atr (NQ override in configs/nq.yaml = 1.8)
    wick_to_body_max: 0.35
    leg_gap_max_bars: 1
```

## 8. Test fixtures

- `tests/fixtures/displacement/strong_bull_bar.csv` — single bar with body 80% of range and body = 2× ATR ⇒ BULL displacement.
- `tests/fixtures/displacement/long_wick_disqualifies.csv` — body 70% of range but top wick > 35% of body ⇒ no displacement.
- `tests/fixtures/displacement/small_body_disqualifies.csv` — body < 1.5× ATR ⇒ no displacement.
- `tests/fixtures/displacement/leg_with_one_gap.csv` — three bull bars with one neutral middle bar (`gap_max=1`) ⇒ single Leg.
- `tests/fixtures/displacement/leg_terminated_by_counter.csv` — bull leg ended by a bear displacement bar ⇒ leg ends at the prior bar.

## 9. Open questions

- **(Q3.a)** Use Wilder ATR or simple-moving-average True Range? **Default v1: Wilder** (matches most charting platforms and ICT material).
- **(Q3.b)** Should `gap_max` count *any* non-displacement bar or only bars without an opposing displacement? **Default v1:** any non-displacement bar; opposing displacement always terminates the leg.

## 10. Cross-references

- Consumed by [02 — MSS](./02_market_structure.md) (mandatory).
- Consumed by [04 — FVG](./04_fair_value_gap.md) as the candidate-leg generator.
- Consumed by [05 — Order Block](./05_order_block.md) for "last opposing candle before displacement".
- Consumed by [06 — Breaker](./06_breaker_block.md) and [14 — Unicorn](./14_unicorn_model.md).
