# 11 — Dealing Range, Premium / Discount, Equilibrium, Optimal Trade Entry (OTE)

> **Status:** spec v1 — pending sign-off
> **Source:** `docs/research/ict_concepts_research.md` §§ "Matrices de Premium y Descuento" and § "El Modelo Unicornio y Estrategias de Confluencia"
> **Cross-reference:** [ictindex.io](https://www.ictindex.io/) — queries *"dealing range", "premium discount", "OTE optimal trade entry"*
> **Implements:** `src/ict_bot/signals/ranges/dealing_range.py`, `signals/ranges/ote.py` (Phase 3)
> **Depends on:** [01 — Swing H/L](./01_swing_points.md), [03 — Displacement](./03_displacement.md)
> **Depended on by:** 09, 14, Phase-4 setups

## 1. Definitions

### 1.1 Dealing Range

The **dealing range** is the active price interval delimited by the most recent confirmed structural extremes (a higher-timeframe swing high and swing low) that bracket the current price. It is the reference frame for Premium/Discount classification and for Fibonacci-based OTE computation.

### 1.2 Premium / Discount / Equilibrium

Given a dealing range `R = [low, high]` with midpoint `eq = (low + high) / 2`:

- **Premium** half = `(eq, high]` — institutional sells.
- **Discount** half = `[low, eq)` — institutional buys.
- **Equilibrium** = `eq` exactly.

The bot **does not** buy in Premium nor sell in Discount (top rule in `STRATEGY.md`).

### 1.3 Optimal Trade Entry (OTE)

OTE is a Fibonacci retracement zone of the active **displacement leg** (concept 03) used to identify the optimal pullback entry. ICT canonical levels: **0.618, 0.705 (sweet spot), 0.79**. The 0.705 level is sometimes called the "golden zone".

## 2. Notation

| Symbol | Meaning |
| ------ | ------- |
| `R = [low, high]`       | Dealing range |
| `eq`                    | Equilibrium of `R` |
| `L`                     | Active displacement leg (with `direction`, `start`, `end`, `range = [leg_low, leg_high]`) |
| `f`                     | Fibonacci retracement level in `[0, 1]` |
| `OTE_zone`              | Interval `[fib(0.618), fib(0.79)]` of `L` |

## 3. Formal definitions

### 3.1 Dealing range construction

The dealing range is computed on a **reference timeframe** `tf_ref` (default `15m` for intraday NQ trading; configurable). At bar close `t`:

```
last_SH = most recent confirmed swing high on tf_ref at or before t
last_SL = most recent confirmed swing low  on tf_ref at or before t

R(t) = [ last_SL.price, last_SH.price ]                 if last_SL.confirmed_at < last_SH.confirmed_at
     = [ last_SL.price, last_SH.price ]                 anyway — the *order* doesn't matter for the interval,
                                                          but the engine also stores which extreme is more recent.

eq(t) = (R.low + R.high) / 2
```

The dealing range is **redefined** when either extreme is invalidated by a body close beyond it (which is a BoS, concept 02).

### 3.2 Premium / Discount classification of a price `p`

```
classify(p) = PREMIUM  if  p > eq
              EQUILIB  if  p == eq
              DISCOUNT if  p < eq
```

### 3.3 OTE on a displacement leg

For a **bullish** leg `L_bull` from `leg_low` to `leg_high` (`leg_high` more recent):

```
fib(f) = leg_high - f × (leg_high - leg_low)              # retracement DOWN from the high
OTE_zone_bull = [ fib(0.79) , fib(0.618) ]
sweet_spot_bull = fib(0.705)
```

For a **bearish** leg `L_bear` from `leg_high` to `leg_low` (`leg_low` more recent):

```
fib(f) = leg_low + f × (leg_high - leg_low)               # retracement UP from the low
OTE_zone_bear = [ fib(0.618) , fib(0.79) ]
sweet_spot_bear = fib(0.705)
```

A bar enters the OTE zone when its low (bullish) or high (bearish) touches the interval. The engine emits an `OTEEntry` event at that bar.

## 4. Detection (pseudocode)

```text
input:
    bars, swings (per TF), legs (concept 03)
    tf_ref:        timeframe for dealing range (default "15m")
    fib_levels:    {0.618, 0.705, 0.79}

# Dealing range tracker
def dealing_range_at(t):
    last_SH = most_recent_swing(tf_ref, kind=HIGH, before_or_at=t)
    last_SL = most_recent_swing(tf_ref, kind=LOW,  before_or_at=t)
    if last_SH is None or last_SL is None:
        return None
    return Range(low=last_SL.price, high=last_SH.price,
                 eq=(last_SH.price + last_SL.price)/2,
                 latest_extreme=max((last_SH, last_SL), key=lambda s: s.confirmed_at))

# OTE on a leg
def ote_zone(leg):
    lo, hi = leg.range_low, leg.range_high
    if leg.direction == BULL:
        return Interval(low=hi - 0.79 * (hi - lo),
                        high=hi - 0.618 * (hi - lo),
                        sweet_spot=hi - 0.705 * (hi - lo))
    else:
        return Interval(low=lo + 0.618 * (hi - lo),
                        high=lo + 0.79 * (hi - lo),
                        sweet_spot=lo + 0.705 * (hi - lo))

# OTE entry detection (used by setups)
def ote_entries(leg, bars):
    z = ote_zone(leg)
    events = []
    for t in bars after leg.end:
        b = bars[t]
        if (leg.direction == BULL and b.low <= z.high and b.low >= z.low) or \
           (leg.direction == BEAR and b.high >= z.low and b.high <= z.high):
            events.append(OTEEntry(t=t, leg=leg, zone=z,
                                   reached_sweet_spot=(z.low <= z.sweet_spot <= z.high
                                                       and ((leg.direction == BULL and b.low <= z.sweet_spot) or
                                                            (leg.direction == BEAR and b.high >= z.sweet_spot)))))
    return events
```

## 5. Invalidation

- **Dealing range** is redefined (not invalidated) whenever a new HTF extreme is confirmed; the previous range becomes historical.
- **OTE on a leg** is invalidated when the leg itself is exhausted (concept 03 §5): a body close past the leg's 50% (= equilibrium of the leg) in the opposing direction kills the OTE zone.

## 6. Confluence rules

- OTE coincident with an FVG, OB, Breaker, or Mitigation Block ⇒ priority entry zone. This is the basis of every V1 setup.
- OTE inside the higher-timeframe **Discount** half (for longs) or **Premium** half (for shorts) ⇒ aligned with bias; otherwise rejected.
- OTE sweet-spot (0.705) being reached carries the highest confidence.
- L2 confirmation (Phase 8): when price enters OTE, `spread_compression` should rise and `delta_acceleration` should begin flipping in the leg's direction.

## 7. Parameters (configs/default.yaml)

```yaml
ranges:
  dealing_range:
    reference_timeframe: "15m"
  ote:
    levels: [0.618, 0.705, 0.79]
    sweet_spot: 0.705
    require_in_correct_half: true   # longs in Discount, shorts in Premium
  fib:
    additional_levels: [0.5, 0.886]  # extension/contraction levels for analysis only
```

## 8. Test fixtures

- `tests/fixtures/ranges/dealing_range_basic.csv` — two confirmed HTF swings ⇒ `R`, `eq`.
- `tests/fixtures/ranges/premium_classification.csv` — series of prices ⇒ each correctly classified PREMIUM/DISCOUNT/EQUILIB.
- `tests/fixtures/ranges/ote_bull_leg.csv` — bullish leg from 100 to 200; OTE zone should be `[100 + 0.21×100, 100 + 0.382×100]` = `[121, 138.2]`, sweet spot `129.5`.
- `tests/fixtures/ranges/ote_bear_leg.csv` — symmetric for bear leg.
- `tests/fixtures/ranges/ote_invalidated_by_leg_50pct.csv` — bear close past leg's 50% kills the bull OTE.

## 9. Open questions

- **(Q11.a)** Reference TF for dealing range — 15m is a common ICT default; should NQ use 5m or 15m? **Default v1:** 15m; expose as config.
- **(Q11.b)** Should we compute OTE on every leg or only on legs that ratified a BoS/MSS? **Default v1:** only legs that ratified a BoS or MSS — same gating as Order Blocks. Other legs are noise.
- **(Q11.c)** OTE sweet-spot tolerance — exact 0.705 or band? **Default v1:** band of `±1 tick` around 0.705 marks "sweet spot hit".

## 10. Cross-references

- Uses swings from [01](./01_swing_points.md) and legs from [03](./03_displacement.md).
- Premium/Discount used by [09 — PD Array hierarchy](./09_pd_array_hierarchy.md) selector.
- OTE consumed by [14 — Unicorn](./14_unicorn_model.md) and Phase-4 setups (OB+OTE, Silver Bullet, etc.).
