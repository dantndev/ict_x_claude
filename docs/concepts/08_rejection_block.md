# 08 — Rejection Block

> **Status:** spec v1 — pending sign-off
> **Source:** `docs/research/ict_concepts_research.md` § "Estructuras de Bloques de Ejecución" (control matrix row "Rejection")
> **Cross-reference:** [ictindex.io](https://www.ictindex.io/) — query *"rejection block"*
> **Implements:** `src/ict_bot/signals/blocks/rejection.py` (Phase 3)
> **Depends on:** [10 — Liquidity (sweep)](./10_liquidity.md)
> **Depended on by:** 09

## 1. Definition

A **Rejection Block** is a fast reversal structure formed at an extreme of the market by a single dominant **wick** (or compact wick cluster) that swept liquidity beyond a swing extreme and then was immediately rejected within the same candle, with the body closing back inside the prior range.

Per the user's research-markdown control matrix:

- **Requires** a fast liquidity sweep (BSL or SSL).
- Reference region = the **wick** of the sweeping candle, **excluding the body**.
- Validation = the body of the same (or next) candle closes back inside the prior market range.
- Entry zone = open/close of the body up to the extreme of the wick.
- SL = one tick beyond the wick's extreme.

## 2. Notation

| Symbol | Meaning |
| ------ | ------- |
| `R`        | Rejection Block object |
| `R.kind`   | `BULL` if the wick swept below an SSL (sweep-low → reject up) ; `BEAR` if the wick swept above a BSL |
| `R.range`  | The wick interval. For bullish: `[L_t, min(O_t, C_t)]`. For bearish: `[max(O_t, C_t), H_t]`. |
| `R.anchor_t` | Index of the wick candle |

## 3. Formal definition

A bar `t` produces a **bullish Rejection Block** when **all** of:

```
1. The bar's wick punctures an active SSL pool:
       L_t  <  SSL_pool.price   AND   min(O_t, C_t) ≥ SSL_pool.price
       (the wick goes below; the body does NOT close below)

2. The body closes back inside the prior bar's range (the rejection):
       min(O_t, C_t)  ≥  L_{t-1}     OR     C_t  ≥  L_{t-1}

3. The bar's lower wick is significantly larger than its body:
       (min(O_t, C_t) - L_t)  /  max(|C_t - O_t|, ε)  ≥  k_wick      (default k_wick = 2.0)
```

Then:

```
R.range = [ L_t , min(O_t, C_t) ]
```

A bearish Rejection Block is the mirror: wick punctures a BSL pool, body closes back inside the prior range, upper wick ≥ `k_wick` × body.

### One-candle vs two-candle variant

ICT material discusses both:

- **One-candle:** sweep + rejection within the same bar (above).
- **Two-candle:** wick sweep on bar `t`, body close back inside prior range on bar `t+1`.

**Default v1:** support both, using `lookforward = 1` bar; emit the Rejection at the bar where the body close completes the reversal.

## 4. Detection (pseudocode)

```text
input:
    bars
    liquidity_pools (from concept 10)
    config: { k_wick, lookforward }

rejections = []
for pool in liquidity_pools:
    for t in pool.active_bars_window:
        if pool.kind == SSL:
            # Wick below pool, body holds
            if bars[t].low < pool.price and min(bars[t].open, bars[t].close) >= pool.price:
                # Check rejection in same or next bar (lookforward)
                for k in 0 .. config.lookforward:
                    candle = bars[t + k]
                    body = abs(candle.close - candle.open)
                    lower_wick = min(candle.open, candle.close) - candle.low
                    if body > 0 and lower_wick / body >= config.k_wick:
                        if candle.close >= bars[t-1].low:
                            R = RejectionBlock(
                                kind=BULL, anchor_t=t,
                                range=[bars[t].low, min(bars[t].open, bars[t].close)],
                                sweep_pool=pool,
                            )
                            rejections.append(R)
                            break
        elif pool.kind == BSL:
            # Symmetric for bearish rejection
            ...
```

## 5. Invalidation

A Rejection Block is invalidated when a later body close pierces **beyond the wick's extreme** in the sweep direction:

```
Bullish Rejection invalidated  ⇔  ∃ s > R.anchor_t :  Close_s  <  R.range.low
Bearish Rejection invalidated  ⇔  ∃ s > R.anchor_t :  Close_s  >  R.range.high
```

Rejection Blocks are the **lowest** rank in the PD Array hierarchy (level 7) and the most fragile — invalidation is common.

## 6. Confluence rules

- Rejection at an HTF swing extreme (D/H4 swing high/low) = much higher quality.
- Rejection inside the OTE zone (concept 11) = stronger.
- Rejection on a Killzone bar (concept 13) = stronger; outside killzones, mostly noise on LTF.
- L2 confirmation (Phase 8): on the wick candle, `obi_top10` should already be flipping away from the wick direction; `spread_compression` elevated.

## 7. Parameters (configs/default.yaml)

```yaml
blocks:
  rejection:
    require_prior_sweep: true
    wick_to_body_min: 2.0        # k_wick
    lookforward_bars: 1
    invalidation: body_close_beyond_wick_extreme
```

## 8. Test fixtures

- `tests/fixtures/rejection/bull_rejection_single_candle.csv` — bar sweeps SSL with long lower wick, body closes back above prior low ⇒ bullish Rejection.
- `tests/fixtures/rejection/bull_rejection_two_candle.csv` — bar `t` sweeps, bar `t+1` body confirms back inside ⇒ Rejection at `t`.
- `tests/fixtures/rejection/no_rejection_body_closes_below.csv` — wick + body close BOTH below the pool ⇒ NOT a Rejection (this is an MSS/Breaker path).
- `tests/fixtures/rejection/rejection_invalidated.csv` — later body close pierces wick low ⇒ invalidated.

## 9. Open questions

- **(Q8.a)** Should the `bars[t-1].low` reference be replaced by `bars[t-1].close` for stricter "back inside" semantics? **Default v1:** `bars[t-1].low` (the entire prior bar's range, more permissive).
- **(Q8.b)** Cluster of consecutive wicks at the same extreme — collapse into one Rejection or treat separately? **Default v1:** collapse into one Rejection (range = union of the wicks), tagged `compound`.

## 10. Cross-references

- Requires [10 — Liquidity sweep](./10_liquidity.md) directly.
- Ranked at level 7 (lowest) in [09 — PD Array hierarchy](./09_pd_array_hierarchy.md).
- Often coincides with [01 — Swing High/Low](./01_swing_points.md) at HTF extremes.
