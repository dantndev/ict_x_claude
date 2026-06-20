# 02 — Market Structure, BoS, ChoCH, MSS

> **Status:** spec v1 — pending sign-off
> **Source:** `docs/research/ict_concepts_research.md` § "Formalización Algorítmica de Estructura de Mercado y Desplazamiento"
> **Cross-reference:** [ictindex.io](https://www.ictindex.io/) — query *"market structure shift", "break of structure", "change of character"*
> **Implements:** `src/ict_bot/structure/market_structure.py` (Phase 3)
> **Depends on:** [01](./01_swing_points.md), [03](./03_displacement.md), [04](./04_fair_value_gap.md), [10](./10_liquidity.md)

## 1. Definition

Market structure is the sequence of confirmed swings interpreted as a **direction state**:

- **Bullish:** sequence of Higher Highs (HH) and Higher Lows (HL).
- **Bearish:** sequence of Lower Lows (LL) and Lower Highs (LH).
- **Ranging:** no consistent ordering between consecutive swings (used for `discard` gating, not entries).

Three named transition events sit on top of structure:

| Event | What it is | Strength |
| ----- | ---------- | -------- |
| **BoS — Break of Structure** | Continuation: a body close beyond the most recent same-side swing in the prevailing trend. | Confirms trend; weak as a reversal signal. |
| **ChoCH — Change of Character** | First break against the prevailing trend (e.g., bullish state → a body close below the last HL). | Notice of regime change; not yet actionable on its own. |
| **MSS — Market Structure Shift** | A ChoCH that additionally exhibits **displacement** AND leaves an **FVG** in the breaking leg, **after** a prior liquidity sweep of the opposite extreme. | Highest-quality reversal signal; the bot's primary trigger. |

## 2. Notation

| Symbol | Meaning |
| ------ | ------- |
| `s_i` | The `i`-th confirmed swing from concept 01 |
| `state ∈ {BULL, BEAR, RANGE}` | Current market-structure regime |
| `last_HH`, `last_HL`, `last_LH`, `last_LL` | Most recent swing of each role |
| `D_t` | Displacement boolean at bar `t` (concept 03) |
| `FVG_t` | Whether the bar `t`'s breaking leg generated an FVG of matching direction (concept 04) |
| `Sweep_t` | Whether a liquidity sweep occurred prior to the break (concept 10) |

## 3. Formal definitions

### 3.1 State machine over swings

Walking through confirmed swings `s_1, s_2, ...` in chronological order, classify each as HH/HL/LH/LL by comparing to the *prior same-kind* swing:

```
For each new swing s_i of kind k:
    prior = last swing of kind k before s_i
    if k == HIGH:
        role = HH if s_i.price > prior.price else LH
    if k == LOW:
        role = HL if s_i.price > prior.price else LL
```

State transitions:

```
state = BULL  if  the latest two swings form (HH, HL)  in either order
state = BEAR  if  the latest two swings form (LH, LL)  in either order
state = RANGE otherwise
```

### 3.2 BoS — Break of Structure (continuation)

In `BULL` state:

```
BoS_bull_t  ⇔  Close_t > last_HH.price   AND   state was BULL just before t
```

Symmetric in `BEAR`:

```
BoS_bear_t  ⇔  Close_t < last_LL.price   AND   state was BEAR just before t
```

**Body close required.** A wick beyond `last_HH` without body close = liquidity sweep, not BoS.

### 3.3 ChoCH — Change of Character (early reversal notice)

```
ChoCH_to_bull_t  ⇔  state was BEAR   AND   Close_t > last_LH.price
ChoCH_to_bear_t  ⇔  state was BULL   AND   Close_t < last_HL.price
```

On a ChoCH event, the state **does not flip yet**; we still need either (a) the next opposite swing to be confirmed, or (b) an MSS-grade break to ratify the reversal.

### 3.4 MSS — Market Structure Shift (the trigger)

```
MSS_bull_t  ⇔  ChoCH_to_bull_t   AND   D_t == true   AND   FVG_bull   on the breaking leg   AND   Sweep_bear in the prior leg
MSS_bear_t  ⇔  ChoCH_to_bear_t   AND   D_t == true   AND   FVG_bear   on the breaking leg   AND   Sweep_bull in the prior leg
```

On an MSS, the state flips deterministically: `BEAR → BULL` (resp. `BULL → BEAR`). This is the gate that opens the Trigger layer of `STRATEGY.md`.

## 4. Detection (pseudocode)

```text
input:
    bars: ordered list of Bar
    swings: ordered list of Swing (from concept 01)
    displacement: function (bars, t) → bool   (concept 03)
    fvg_on_leg: function (bars, leg) → {BULL, BEAR, NONE}  (concept 04)
    sweep_in_prior_leg: function (bars, t, opposite_side) → bool  (concept 10)

state = RANGE
last = { HH: None, HL: None, LH: None, LL: None }

# Update roles as swings confirm
for s in swings (in confirm order):
    classify(s) → role
    update last[role]
    update state

# For each new bar close, emit events
for t in close_order:
    if last.HH and Close_t > last.HH.price and state == BULL:
        emit BoS(bull, t)
    if last.LL and Close_t < last.LL.price and state == BEAR:
        emit BoS(bear, t)

    if state == BEAR and last.LH and Close_t > last.LH.price:
        if displacement(bars, t) and fvg_on_leg(bars, leg=t) == BULL \
           and sweep_in_prior_leg(bars, t, opposite_side=SSL):
            emit MSS(bull, t)
            state = BULL
        else:
            emit ChoCH(to_bull, t)

    if state == BULL and last.HL and Close_t < last.HL.price:
        if displacement(bars, t) and fvg_on_leg(bars, leg=t) == BEAR \
           and sweep_in_prior_leg(bars, t, opposite_side=BSL):
            emit MSS(bear, t)
            state = BEAR
        else:
            emit ChoCH(to_bear, t)
```

## 5. Invalidation

- **BoS** is invalidated if a subsequent body close re-crosses the broken swing in the opposite direction within `K` bars (config `structure.bos_invalidation_lookahead`, default `5`). Tracked but does not undo the historical event.
- **ChoCH** is invalidated if the next confirmed swing fails to set up the new direction within `K_choch` bars (default `8`) — the engine returns to the prior state without committing to a flip.
- **MSS** is *not invalidated* once emitted (it's the strongest signal). But the trade it triggers can be invalidated by SL hit — that is a risk concern, not a structural one.

## 6. Confluence rules

- An MSS gains weight if it occurs:
  - Inside an HTF PD Array (H4/D OB, FVG, Breaker).
  - Inside a Killzone (concept 13).
  - With strong L2 confirmation (delta acceleration matching MSS direction, OBI flip).
- A BoS without an FVG on the breaking leg is downgraded to "weak BoS" (do not chase).

## 7. Parameters (configs/default.yaml)

```yaml
structure:
  bos_require_body_close: true
  bos_invalidation_lookahead: 5
  choch_invalidation_lookahead: 8
  mss:
    require_displacement: true
    require_fvg_on_breaking_leg: true
    require_prior_opposite_sweep: true
```

## 8. Test fixtures

- `tests/fixtures/structure/bull_state_hh_hl.csv` — four swings ordered HH/HL/HH/HL → state BULL.
- `tests/fixtures/structure/bos_bull_body_close.csv` — clean body close above last_HH → BoS(bull).
- `tests/fixtures/structure/bos_wick_not_close.csv` — wick beyond last_HH but body inside → no BoS, sweep tag instead (concept 10).
- `tests/fixtures/structure/choch_bear_to_bull.csv` — bear state, body close above last_LH, no displacement → ChoCH only.
- `tests/fixtures/structure/mss_bull_full.csv` — bear state → sweep of SSL → close above last_LH with displacement and FVG → MSS(bull).
- `tests/fixtures/structure/mss_bull_missing_fvg.csv` — same as above but no FVG → ChoCH only, not MSS.

## 9. Open questions

- **(Q2.a)** When a swing is *redefined* by a higher-magnitude later swing of the same kind (e.g., HH gets superseded by a higher HH within 1-2 bars), does the engine update `last_HH` immediately or wait for the original swing's `confirmed_at_index`? **Default v1:** wait for confirmation; do not reorder retroactively.
- **(Q2.b)** Should ChoCH count toward the trigger layer at all, or only MSS? **Default v1:** only MSS triggers entries; ChoCH is logged for observability and may be used by Phase 8 ML.

## 10. Cross-references

- Requires confirmed swings from [01](./01_swing_points.md).
- Requires displacement from [03](./03_displacement.md).
- Requires FVG detector from [04](./04_fair_value_gap.md).
- Requires liquidity-sweep detection from [10](./10_liquidity.md).
- Triggers entries described in [14 — Unicorn](./14_unicorn_model.md) and other setups.
