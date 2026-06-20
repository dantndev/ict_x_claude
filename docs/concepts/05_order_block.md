# 05 — Order Block + Mean Threshold

> **Status:** spec v1 — pending sign-off
> **Source:** `docs/research/ict_concepts_research.md` § "Estructuras de Bloques de Ejecución"
> **Cross-reference:** [ictindex.io](https://www.ictindex.io/) — query *"order block", "mean threshold", "bullish order block", "bearish order block"*
> **Implements:** `src/ict_bot/signals/blocks/order_block.py` (Phase 3)
> **Depends on:** [01](./01_swing_points.md), [02](./02_market_structure.md), [03](./03_displacement.md), [04](./04_fair_value_gap.md)
> **Depended on by:** 06, 07, 09, 14

## 1. Definition

An **Order Block (OB)** is the last opposing candle (or compact group of consecutive opposing candles) immediately preceding a displacement leg that ruptures structure (BoS) in one direction. Institutionally interpreted: it is the price region where the IPDA accumulated/distributed before injecting the move.

- **Bullish OB** — last bearish candle before a bullish displacement that breaks structure upward.
- **Bearish OB** — last bullish candle before a bearish displacement that breaks structure downward.

The **Mean Threshold (MT)** is the OB's midpoint and the primary invalidation level for the body-close rule.

## 2. Notation

| Symbol | Meaning |
| ------ | ------- |
| `OB`              | Order block object — has `kind`, `range = [low, high]`, `anchor_t`, `displacement_leg_ref` |
| `H_OB, L_OB`      | OB's high and low |
| `MT_OB`           | Mean threshold |
| `Open_OB`         | Open of the OB candle (used in "open-to-MT" entry variant) |

## 3. Formal definition

### 3.1 Identification

Walking the bar series forward, when a **bullish displacement leg** `L` is detected (concept 03) AND that leg's body close ratifies a **BoS-bull** (concept 02):

```
Bullish_OB candidate
    = last contiguous run of bars { b_j, b_{j+1}, ..., b_k }  with
          k = first bar of L
        and  each b_i ∈ run  is  bearish  (Close_i < Open_i)
```

If the run is empty (the bar immediately before the leg is bullish), use **the bar with the lowest low** within a `lookback` window (default 5 bars) prior to the leg — this captures the "extremum-bar" variant some ICT teachers prefer. The default in v1: prefer the contiguous-opposing-run definition; fall back to the extremum-bar only if the run is empty.

For the **bearish OB**, mirror: a bearish displacement leg ratifying a BoS-bear, preceded by the last contiguous run of bullish candles.

OB range:

```
OB.range = [ min(Low_i) , max(High_i) ]      over the run
MT_OB    = OB.range.low + 0.5 × (OB.range.high − OB.range.low)
```

### 3.2 Validity gating

A candidate OB is **valid** only if:

1. The displacement leg that follows it generates an **FVG** of the matching direction (per concept 04).
2. The displacement leg ratifies a **BoS** (per concept 02). A leg without a BoS demotes the OB to "weak OB" — kept in registry but not eligible for entries.
3. The OB lies in confluence with a higher-timeframe target (per `STRATEGY.md`): if no HTF anchor (HTF OB, FVG, liquidity pool, OTE zone), the OB is tagged `unanchored` and excluded from V1 entries. (User-set rule from research markdown: "must be generated in confluence with a higher-timeframe objective".)

## 4. Detection (pseudocode)

```text
input:
    bars, swings, legs (from concept 03), bos_events (from concept 02),
    fvg_lookup(leg) → FVG | None
    htf_anchors(bar_index) → list of HTF references at this price

obs = []

for leg in legs:
    if not has_bos(leg):                  # leg must ratify a BoS
        continue
    fvg = fvg_lookup(leg)
    if fvg is None:
        continue
    # walk back from leg.start to gather opposing-direction contiguous bars
    run = []
    i = leg.start - 1
    opp = BEAR if leg.direction == BULL else BULL
    while i >= 0 and bar_dir(bars[i]) == opp:
        run.append(i)
        i -= 1
        if len(run) >= max_run_bars: break
    if not run:
        # fall back to extremum-bar within lookback
        run = [argmin_low(bars, leg.start - lookback, leg.start - 1)] if leg.direction == BULL \
              else [argmax_high(bars, leg.start - lookback, leg.start - 1)]
    ob_range = [ min(bars[i].low for i in run), max(bars[i].high for i in run) ]
    ob = OrderBlock(
        kind = BULL if leg.direction == BULL else BEAR,
        anchor_t = min(run),
        range = ob_range,
        mt = midpoint(ob_range),
        leg_ref = leg,
        fvg_ref = fvg,
        htf_anchor = htf_anchors(min(run)),
    )
    if ob.htf_anchor is None:
        ob.tag = "unanchored"
    obs.append(ob)
```

## 5. Invalidation

A valid OB is invalidated when **a later bar's body closes beyond its Mean Threshold** in the opposing direction:

```
Bullish OB invalidated  ⇔  ∃ s > anchor_t :  Close_s  <  MT_OB
Bearish OB invalidated  ⇔  ∃ s > anchor_t :  Close_s  >  MT_OB
```

Wicks that puncture MT but reverse before close are tolerated. Body-close invalidation is consistent with the user's research markdown ("Cierre de cuerpo de vela más allá de su Umbral Medio (MT)").

Once invalidated, the OB may later qualify as a **Breaker Block** (see concept 06) — the engine therefore moves invalidated OBs into a `breaker_candidates` registry rather than discarding them.

## 6. Confluence rules

- OB inside the **OTE zone** of the active dealing range (concept 11) is the strongest standalone setup.
- OB overlapping an **FVG** of the same direction = high-confluence (see [14 — Unicorn](./14_unicorn_model.md) for the Breaker variant).
- OB at the open price (extremum-bar variant whose open coincides with MT) is tagged `open=MT`, used in the "open-to-MT" entry style.
- OB tagged `unanchored` (no HTF context) is **not traded** by V1.

## 7. Parameters (configs/default.yaml)

```yaml
blocks:
  order_block:
    require_displacement: true
    require_fvg_on_following_leg: true
    require_htf_anchor: true            # v1 enforces top-down validation
    max_run_bars: 4                     # max length of the opposing-bar run
    extremum_fallback_lookback: 5
    invalidation: body_close_beyond_mt
    entry_style: edge_or_mt              # "edge" = use proximal extreme; "mt" = MT
```

## 8. Test fixtures

- `tests/fixtures/ob/bullish_ob_single_bear_bar.csv` — one bear bar then bullish displacement leg + FVG + BoS ⇒ one bullish OB with `range = [L_bear, H_bear]`.
- `tests/fixtures/ob/bullish_ob_contiguous_run.csv` — three consecutive bear bars then displacement ⇒ OB range spans the run.
- `tests/fixtures/ob/bullish_ob_no_fvg_demoted.csv` — leg breaks structure but leaves no FVG ⇒ OB tagged "weak", not eligible.
- `tests/fixtures/ob/bullish_ob_unanchored.csv` — valid OB but no HTF anchor at price ⇒ tagged `unanchored`, excluded from active set.
- `tests/fixtures/ob/bullish_ob_invalidated_by_body_below_mt.csv` — later bar body closes below MT ⇒ invalidated, moves to breaker_candidates.

## 9. Open questions

- **(Q5.a)** Run definition: contiguous bars of opposing direction, OR contiguous bars *without breaking* in the leg's direction (closer to a "rectangle")? **Default v1:** opposing-direction contiguous run with fallback to extremum bar.
- **(Q5.b)** `max_run_bars` cap — should it be infinite when each bar in the run also satisfies `body / range ≥ threshold`? **Default v1:** hard cap at 4 to avoid huge OBs.
- **(Q5.c)** Should we allow re-entry into a "fresh" OB (one that has not yet been tested) but reject "stale" ones (already mitigated once)? **Default v1:** track `touch_count`; eligible only when `touch_count == 0`.

## 10. Cross-references

- Generates [06 — Breaker](./06_breaker_block.md) candidates on invalidation.
- Composes with FVG in [14 — Unicorn](./14_unicorn_model.md).
- Ranked at level 6 in [09 — PD Array hierarchy](./09_pd_array_hierarchy.md).
