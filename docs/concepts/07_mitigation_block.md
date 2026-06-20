# 07 — Mitigation Block

> **Status:** spec v1 — pending sign-off
> **Source:** `docs/research/ict_concepts_research.md` § "Estructuras de Bloques de Ejecución" (control matrix row "Mitigation")
> **Cross-reference:** [ictindex.io](https://www.ictindex.io/) — query *"mitigation block"*
> **Implements:** `src/ict_bot/signals/blocks/mitigation.py` (Phase 3)
> **Depends on:** [05](./05_order_block.md), [02](./02_market_structure.md)
> **Depended on by:** 09

## 1. Definition

A **Mitigation Block** is a **continuation** structure (contrast: Breaker = reversal). It is an old Order Block that the market *failed to invalidate* — typically because the displacement leg that followed it created an FVG/imbalance that price never closed beyond. On the next deep retrace, price returns to the OB's body and the OB is "mitigated" (visited, partially filled, respected), producing a continuation move in the original direction.

Crucially, per the user's research-markdown control matrix, a Mitigation Block:

- **Does not require** a prior liquidity sweep (this is the key distinction from a Breaker).
- Is a **swing-failure** structure: the price failed to sweep the opposite extreme.
- Reference region = body of the OB that is being respected.
- Entry = at the OB body limit on the retest.
- SL = behind the OB's extreme.

## 2. Notation

| Symbol | Meaning |
| ------ | ------- |
| `OB`        | Order Block from concept 05 |
| `M`         | Mitigation Block — same range as `OB` but tagged at the time of its first respected retest |
| `M.touch_t` | Bar index of first retest that respects the OB |

A Mitigation Block is not a *new* structure spatially — it is a *labelling* applied to an OB after a successful retest with no prior sweep.

## 3. Formal definition

Given a valid (active, non-invalidated) `OB` from concept 05, scan for the first bar `s > OB.anchor_t` such that:

```
Price returns into OB.range:
    (OB.kind == BULL  AND  Low_s  ≤  OB.range.high)
    (OB.kind == BEAR  AND  High_s ≥  OB.range.low)

AND no body close has invalidated OB (concept 05 invalidation rule did not fire)

AND no liquidity sweep occurred against OB's direction between OB.anchor_t and s
    (i.e., NO BSL/SSL sweep with `s_sweep ∈ (OB.anchor_t, s)`  — this is what distinguishes
    Mitigation from Breaker)
```

When such `s` exists, register:

```
M = MitigationBlock(
    origin_ob = OB,
    kind      = OB.kind,
    range     = OB.range,
    mt        = OB.mt,
    touch_t   = s,
)
```

## 4. Detection (pseudocode)

```text
input:
    active_obs:  list of currently-active OBs
    sweeps:       registry from concept 10
    bars:         ordered series

mitigations = []
for OB in active_obs:
    # find first retest after anchor
    s = first index > OB.anchor_t where
            (OB.kind == BULL and bars[s].low  ≤ OB.range.high) or
            (OB.kind == BEAR and bars[s].high ≥ OB.range.low)
    if s is None:
        continue

    # ensure no sweep in the interim against OB's direction
    against_side = SSL if OB.kind == BULL else BSL
    had_sweep = any(sweep.side == against_side and OB.anchor_t < sweep.t < s
                    for sweep in sweeps)
    if had_sweep:
        # This becomes a Breaker candidate path, not a Mitigation
        continue

    # confirm respect: within retest window, no body close invalidates OB
    if not invalidation_fires_in_window(OB, window=[s, s + W_grace]):
        mitigations.append(MitigationBlock(origin_ob=OB, touch_t=s, ...))
```

Where `W_grace` (config) is a small window (default 3 bars) within which the OB must hold for the retest to count as "respected".

## 5. Invalidation

A registered Mitigation Block is invalidated by the same rule as the underlying OB (concept 05): body close beyond Mean Threshold in the opposing direction. The label is removed and the block transitions to the OB invalidation path (which may then qualify as a Breaker if a prior sweep materializes — but typically by then the sequence is over).

Additionally, a Mitigation that has been touched once (`touch_count ≥ 1`) is considered **mitigated** and `touch_count` resets the OB's freshness. V1 treats only fresh OBs (`touch_count == 0`) as eligible mitigation candidates; once the Mitigation entry fires, the underlying OB is consumed.

## 6. Confluence rules

- Mitigation Block inside an OTE zone (concept 11) is a strong continuation entry.
- Mitigation aligned with HTF direction (HTF state matches the OB's kind) is amplified.
- Mitigation contradicting HTF direction is downgraded — the engine prefers Breaker-style reversal setups in that regime.
- L2 confirmation (Phase 8): on the touch bar, `delta_acceleration` should resume in the OB's direction; otherwise tag `unconfirmed`.

## 7. Parameters (configs/default.yaml)

```yaml
blocks:
  mitigation:
    require_prior_sweep: false
    retest_grace_bars: 3              # W_grace
    require_no_intervening_invalidation: true
    only_fresh_obs: true              # touch_count == 0 required
    invalidation: body_close_beyond_mt
```

## 8. Test fixtures

- `tests/fixtures/mitigation/bull_mitigation_no_prior_sweep.csv` — bullish OB, no SSL sweep after, price retraces into OB and continues up ⇒ Mitigation registered.
- `tests/fixtures/mitigation/no_mitigation_when_sweep_intervenes.csv` — same setup but an SSL sweep occurs between OB anchor and retest ⇒ NOT a Mitigation (Breaker path instead).
- `tests/fixtures/mitigation/mitigation_invalidated_by_body_below_mt.csv` — Mitigation registered, then body close below MT ⇒ invalidated.

## 9. Open questions

- **(Q7.a)** Does a *partial* retrace that misses the OB body but reaches MT count as a mitigation candidate? Research markdown is ambiguous. **Default v1:** require touch of the OB's range (not MT) — stricter.
- **(Q7.b)** What if the OB's retest occurs after the bot has *already* entered on a different setup in the opposite direction? Concurrent-position management is a Phase 5/6 concern; for V1 detector tests, we emit the Mitigation regardless and let the engine decide what to do with it.

## 10. Cross-references

- Lineage from [05 — Order Block](./05_order_block.md).
- Contrast with [06 — Breaker](./06_breaker_block.md) (Mitigation = no prior sweep; Breaker = prior sweep).
- Ranked at level 3 in [09 — PD Array hierarchy](./09_pd_array_hierarchy.md).
