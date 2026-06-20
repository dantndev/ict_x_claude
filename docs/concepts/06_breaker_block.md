# 06 — Breaker Block

> **Status:** spec v1 — pending sign-off
> **Source:** `docs/research/ict_concepts_research.md` § "Estructuras de Bloques de Ejecución" (control matrix row "Breaker")
> **Cross-reference:** [ictindex.io](https://www.ictindex.io/) — query *"breaker block"*
> **Implements:** `src/ict_bot/signals/blocks/breaker.py` (Phase 3)
> **Depends on:** [05](./05_order_block.md), [10](./10_liquidity.md), [02](./02_market_structure.md)
> **Depended on by:** 09, 14

## 1. Definition

A **Breaker Block** is a **failed Order Block** that the market subsequently broke through and which now acts as a reversal level. Lineage:

1. A prior OB forms in one direction.
2. Price *fails to hold* the OB — the body closes through it after a liquidity sweep of the opposite-side pool.
3. The broken OB now flips role: it becomes a Breaker that the market will retest in the opposite direction.

Per the user's research-markdown control matrix, the Breaker:

- **Requires** a prior liquidity sweep on the opposite extreme.
- Reference region = body of the **invalidated** OB.
- Validation = body of the validating candle closed **beyond** the original OB.
- Entry = at the OB body limit (now the Breaker's proximal edge).
- SL = behind the high/low of the liquidity sweep.

## 2. Notation

| Symbol | Meaning |
| ------ | ------- |
| `OB*` | Invalidated OB (from concept 05's registry of `breaker_candidates`) |
| `B`   | Breaker Block produced from `OB*` |
| `B.range = OB*.range` (initial) | Inherited from the broken OB |
| `B.kind` | Opposite direction to `OB*.kind` (a bullish OB that breaks down → bearish Breaker that pushes price back down on retest) |

## 3. Formal definition

A Breaker is created when an OB `OB*` is invalidated **AND** the chronological sequence satisfies all of:

```
Step 1: at time s0,  a liquidity sweep occurs against OB*'s direction
          (concept 10: a wick beyond a documented liquidity pool with no body close)

Step 2: at time s1 > s0,  bars push toward OB* in OB*'s creation direction,
          attempting to mitigate it

Step 3: at time s2 > s1,  a body close occurs beyond OB* in the direction OPPOSITE
          to OB*.kind:
              if OB*.kind == BULL:    Close_{s2}  <  MT_{OB*}    (or  L_{OB*}  per strict variant)
              if OB*.kind == BEAR:    Close_{s2}  >  MT_{OB*}
```

The Breaker is then registered:

```
B.kind         = opposite(OB*.kind)
B.range        = OB*.range
B.mt           = MT(OB*.range)
B.sweep_ref    = the sweep at s0
B.invalidator  = s2
```

### Direction nuance (important)

A *bullish* Breaker is what you trade for a **long** entry. It originates from a **bearish OB** that was broken to the upside after an SSL sweep. Symmetric for bearish Breakers.

So in the engine:

| Direction of trade | Originating OB | Required prior sweep |
| ------------------ | -------------- | -------------------- |
| Long (bull Breaker) | bearish OB    | SSL sweep            |
| Short (bear Breaker)| bullish OB    | BSL sweep            |

## 4. Detection (pseudocode)

```text
input:
    breaker_candidates: registry of invalidated OBs (from concept 05)
    sweeps:             registry of liquidity sweeps (from concept 10)
    bars:               ordered series

breakers = []
for OB_star in breaker_candidates:
    # Look back for a sweep occurring before OB_star invalidation,
    # of the side OPPOSITE the OB's direction
    required_side = SSL if OB_star.kind == BULL else BSL
    prior_sweep = first sweep in sweeps where
                      sweep.side == required_side and
                      sweep.t < OB_star.invalidated_at and
                      sweep.t > OB_star.anchor_t
    if prior_sweep is None:
        continue

    B = BreakerBlock(
        kind = BEAR if OB_star.kind == BULL else BULL,
        range = OB_star.range,
        mt = midpoint(OB_star.range),
        sweep_ref = prior_sweep,
        invalidator = OB_star.invalidated_at,
        origin_ob = OB_star,
    )
    breakers.append(B)
```

## 5. Invalidation

A Breaker is **invalidated** when, after its registration, a later body close penetrates beyond its **far** edge (the edge opposite to the proximal entry edge):

```
Bullish Breaker invalidated  ⇔  ∃ s > B.invalidator :  Close_s  <  B.range.low
Bearish Breaker invalidated  ⇔  ∃ s > B.invalidator :  Close_s  >  B.range.high
```

(Some ICT material uses MT instead of the far edge; v1 uses the far edge as the stricter, simpler rule. MT-based invalidation is available as `invalidation_mode: mt` in config for experimentation.)

## 6. Confluence rules

- Breaker that overlaps a **fresh same-direction FVG** = **Unicorn Model** (concept 14) — the highest-priority composition in V1.
- Breaker formed inside the OTE zone of the dealing range (concept 11) is a high-priority standalone trade.
- Breaker contradicted by an HTF PD Array of higher rank is downgraded.
- L2 confirmation (Phase 8): on the retest bar, `obi_top10` should flip in the Breaker's trade direction and `spread_compression` should be elevated.

## 7. Parameters (configs/default.yaml)

```yaml
blocks:
  breaker:
    require_prior_sweep: true
    invalidation_mode: far_edge          # "far_edge" | "mt"
    entry_edge: proximal                  # entry at the edge nearer the current price
    sl_anchor: sweep_extreme              # SL placed behind the sweep's extreme
```

## 8. Test fixtures

- `tests/fixtures/breaker/bull_breaker_after_ssl_sweep.csv`
  - Bullish OB forms, then SSL sweep below, then body close above OB → bullish Breaker registered. (Note: convention — see §3 direction nuance.)
- `tests/fixtures/breaker/bear_breaker_after_bsl_sweep.csv` — symmetric.
- `tests/fixtures/breaker/no_breaker_without_sweep.csv` — OB invalidated cleanly without a preceding sweep ⇒ no Breaker, just a discarded OB.
- `tests/fixtures/breaker/breaker_invalidated_far_edge.csv` — Breaker registered, then a later body close pierces the far edge ⇒ invalidated.

## 9. Open questions

- **(Q6.a)** Strict definition of "body close beyond OB": use OB high/low (extremes) or OB MT? Research markdown says "beyond the block initial body". **Default v1:** the *body* of the validation candle closes beyond the OB's extreme on the side it's breaking through (the high for a bullish-OB→bearish-breaker flip; the low for the mirror).
- **(Q6.b)** Time-decay: should a Breaker auto-expire if not retested within `N` bars? ICT material does not specify. **Default v1:** no auto-expiry; rely on invalidation rule only. Add a `max_age_bars` config (`null` by default) for future tuning.
- **(Q6.c)** Multiple sweeps prior to invalidation — pick the most recent or the deepest? **Default v1:** most recent (closest in time to the break) — that's the one whose stops the IPDA just collected.

## 10. Cross-references

- Successor of an invalidated [05 — Order Block](./05_order_block.md).
- Requires a [10 — Liquidity sweep](./10_liquidity.md) in the prior leg.
- Composed with [04 — FVG](./04_fair_value_gap.md) in [14 — Unicorn](./14_unicorn_model.md).
- Ranked at level 2 in [09 — PD Array hierarchy](./09_pd_array_hierarchy.md).
