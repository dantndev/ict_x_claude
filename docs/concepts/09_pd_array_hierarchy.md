# 09 — PD Array Hierarchy & Invalidation Matrix

> **Status:** spec v1 — pending sign-off
> **Source:** `docs/research/ict_concepts_research.md` § "Matrices de Premium y Descuento"
> **Cross-reference:** [ictindex.io](https://www.ictindex.io/) — query *"PD array", "premium discount arrays"*
> **Implements:** `src/ict_bot/signals/__init__.py` (selector function) and a shared `pd_array` model in `signals/base.py` (Phase 3)
> **Depends on:** [04](./04_fair_value_gap.md), [05](./05_order_block.md), [06](./06_breaker_block.md), [07](./07_mitigation_block.md), [08](./08_rejection_block.md), [10](./10_liquidity.md), [11](./11_dealing_range_ote.md)

## 1. Definition

A **PD Array** (Premium/Discount Array) is any algorithmic level where the IPDA tends to deliver price. The bot maintains a typed registry of every active PD Array at every moment in time, ranked by a strict **hierarchy** that determines:

- Which PD Array dominates when two are at the same price.
- Which PD Array's invalidation rule fires first.
- Which entries the engine considers when price reaches a zone of multiple overlapping arrays.

The hierarchy is taken verbatim from the user's research markdown:

| Rank | Premium-side (sell) | Discount-side (buy) | Invalidation |
| ---- | ------------------- | ------------------- | ------------ |
| 1 (highest) | Prior structural high | Prior structural low | Body close beyond the level |
| 2 | Bearish Breaker Block | Bullish Breaker Block | Body close beyond block's far edge (or MT — config) |
| 3 | Bearish Mitigation Block | Bullish Mitigation Block | Body close beyond block's MT |
| 4 | Weekly / Daily Opening Gap (premium use) | Weekly / Daily Opening Gap (discount use) | Body close that fully fills the gap |
| 5 | SIBI (bearish FVG) | BISI (bullish FVG) | Body close beyond CE |
| 6 | Bearish Order Block | Bullish Order Block | Body close beyond MT |
| 7 (lowest) | Bearish Rejection Block | Bullish Rejection Block | Body close beyond wick extreme |

**Universal validity rule:** A PD Array on a low timeframe **without** an HTF target driving it is rejected as `unanchored` and excluded from entries (per `STRATEGY.md` and concept 05 §3.2).

## 2. Notation

| Symbol | Meaning |
| ------ | ------- |
| `A`             | A PD Array of any kind |
| `A.rank`        | Integer 1..7 |
| `A.side`        | `PREMIUM` (sell-side) or `DISCOUNT` (buy-side) |
| `A.range`       | Price interval `[low, high]` |
| `A.invalidate(s)` | Predicate: did bar `s` invalidate `A`? |
| `Z(p)`          | Set of all active PD Arrays containing price `p` |

## 3. Formal definition

### 3.1 Active set

The engine maintains, at each bar close `t`:

```
ACTIVE_t  =  { A : A.created_at ≤ t  AND  not A.invalidated_by ∈ [A.created_at .. t] }
```

For any price `p` and direction `dir ∈ {BUY, SELL}`:

```
Z_t(p, dir) = { A ∈ ACTIVE_t :  p ∈ A.range  AND  A.side matches dir }
```

(`A.side == DISCOUNT` for `dir == BUY`; `A.side == PREMIUM` for `dir == SELL`.)

### 3.2 Dominance

When `|Z_t(p, dir)| ≥ 2`, the **dominant** PD Array is the one with the **lowest `rank`** (highest priority):

```
dominant_t(p, dir)  =  argmin_{A ∈ Z_t(p, dir)} A.rank
```

Ties (same rank, same price) are broken by recency: later `created_at` wins (a fresher PD Array of equal rank is preferred).

### 3.3 Invalidation cascade

When a body close at bar `s` satisfies `A.invalidate(s)` for an active `A`:

```
ACTIVE_s  ←  ACTIVE_{s-1}  \  {A}
HISTORY   ←  HISTORY  ∪  {(A, s)}
```

For Order Blocks (rank 6), invalidation pushes `A` into `breaker_candidates` (concept 06) for possible promotion.

### 3.4 HTF anchor requirement

```
For every A ∈ ACTIVE_t :
    A.eligible_for_entry  ⇔  A.htf_anchor ≠ ∅
```

`htf_anchor` is computed at creation time and stored on `A`. The check is:

```
A.htf_anchor = {
    H : H ∈ ACTIVE_HTF_t  AND  H.range intersects A.range
}
```

where `ACTIVE_HTF_t` is the active set on the HTF reference (D, H4, H1 per config).

## 4. Detection (pseudocode)

```text
# Registry is updated by each concept-specific detector emitting/invalidating.
# This selector consumes the registry to answer "what's at this price now?"

function pd_arrays_at(price, direction, t):
    candidates = [A for A in ACTIVE[t]
                  if price in A.range
                  and A.side matches direction
                  and A.eligible_for_entry]
    return sorted(candidates, key=lambda A: (A.rank, -A.created_at))

function dominant_pd_array_at(price, direction, t):
    cands = pd_arrays_at(price, direction, t)
    return cands[0] if cands else None
```

Used by setup composers (Phase 4) to query "is this entry zone backed by a top-3 PD Array?" etc.

## 5. Invalidation

This concept has no own invalidation — it composes the invalidation rules of the underlying primitives. The matrix above is the **single source of truth** for what each rank's invalidation predicate looks like; individual concept docs (04–08, 10–11) implement those predicates.

## 6. Confluence rules

- **Stacked PD Arrays** (multiple active arrays at the same price, different ranks) → confluence score = `Σ (8 − rank)` over the stack; tiebreak between candidate setups uses this score.
- **Conflicting PD Arrays** (an Active PREMIUM and an Active DISCOUNT both containing the same price) → the engine treats the price as a `pivot zone` and refuses both directions until one side invalidates.
- **HTF stacking**: a PD Array on D/H4 surrounding the current LTF setup amplifies confidence.

## 7. Parameters (configs/default.yaml)

```yaml
pd_arrays:
  require_htf_anchor: true
  htf_reference_timeframes: ["1H", "4H", "1D"]
  ranking:                       # the canonical hierarchy; overridable for ablation studies
    structural_extreme: 1
    breaker:            2
    mitigation:         3
    opening_gap:        4
    fvg:                5
    order_block:        6
    rejection:          7
  dominance_tiebreaker: recency  # "recency" | "size"
```

## 8. Test fixtures

- `tests/fixtures/pd/dominance_breaker_over_fvg.csv` — Breaker (rank 2) and FVG (rank 5) overlap at price `p` ⇒ `dominant_pd_array_at(p, BUY)` returns the Breaker.
- `tests/fixtures/pd/tiebreaker_recency.csv` — two OBs (rank 6) at same price; later one wins.
- `tests/fixtures/pd/unanchored_excluded.csv` — valid FVG but no HTF anchor ⇒ excluded from `pd_arrays_at`.
- `tests/fixtures/pd/conflicting_premium_discount.csv` — a BISI and a SIBI co-located at the same price (the BPR case from concept 04) ⇒ both returned but selector flags as `pivot_zone`.

## 9. Open questions

- **(Q9.a)** Should the engine *promote* an FVG to higher rank when it sits on a Daily Opening Gap? **Default v1:** no; track confluence as a *score*, not by reordering rank.
- **(Q9.b)** "Opening Gap" rank-4 — the user's research markdown mentions it as a PD Array but no detector spec for it yet exists in concepts 01–08. **Action:** add `signals/imbalance/opening_gap.py` to Phase 3; minimal spec: gap between prior session close and next session open on D/W timeframes. Defer the full opening-gap spec to a v1.1 addendum unless flagged sooner.
- **(Q9.c)** Premium/Discount classification of an A that *straddles* the dealing-range equilibrium (one half above, one half below) — what side does it count as? **Default v1:** classify by `mid(A.range)` vs `equilibrium`.

## 10. Cross-references

- Aggregates [04](./04_fair_value_gap.md), [05](./05_order_block.md), [06](./06_breaker_block.md), [07](./07_mitigation_block.md), [08](./08_rejection_block.md), [10](./10_liquidity.md), [11](./11_dealing_range_ote.md).
- Consumed by every setup in Phase 4 via the selector functions in §4.
