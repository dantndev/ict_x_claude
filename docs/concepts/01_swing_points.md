# 01 — Swing High / Swing Low

> **Status:** spec v1 — pending sign-off
> **Source:** `docs/research/ict_concepts_research.md` § "Formalización Algorítmica de Estructura de Mercado y Desplazamiento"
> **Cross-reference:** [ictindex.io](https://www.ictindex.io/) — query *"swing high swing low fractal"*
> **Implements:** `src/ict_bot/structure/swings.py` (Phase 3)
> **Depends on:** — (foundational)
> **Depended on by:** 02, 05, 06, 07, 08, 10, 11

## 1. Definition

A **swing high** (SH) is a local maximum of the price action — a bar whose high is strictly greater than the highs of a defined number of bars on either side. A **swing low** (SL) is the symmetric definition for local minima. ICT uses swings as the geometric anchor for everything structural: trends, breaks, order blocks, liquidity pools.

ICT material discusses two common widths:

- **3-bar fractal** (also called "Bill Williams fractal" by external sources but used by ICT): one bar on each side.
- **N-bar fractal**: `N` bars on each side, `N ≥ 1`.

The 3-bar form is the most permissive and detects the most swings; larger `N` filters noise but lags more. The bot exposes `N` as a config parameter.

## 2. Notation

| Symbol | Meaning |
| ------ | ------- |
| `High_t`, `Low_t` | High and low of bar at index `t` (after NY tz normalization) |
| `N` | Half-width of the fractal window (`N ≥ 1`) |
| `SH_t`, `SL_t` | Indicator predicates — true iff bar `t` is a swing high / swing low |

## 3. Formal definition

**Swing High of width `N`:**

```
SH_t  ⇔  ∀ k ∈ [1..N] :  High_t  >  High_{t-k}   ∧   High_t  >  High_{t+k}
```

**Swing Low of width `N`:**

```
SL_t  ⇔  ∀ k ∈ [1..N] :  Low_t   <  Low_{t-k}    ∧   Low_t   <  Low_{t+k}
```

A swing is **confirmed** at the close of bar `t + N` (we need `N` future bars). Earlier than that, it is *provisional*. The detector must distinguish the two states — backtests must not "look ahead" by treating a provisional swing as confirmed.

### Tie-breaking (equal highs/lows)

ICT material is not crisp on equals; competing conventions:

- **Strict** (`>` / `<`): equal highs disqualify the swing. Risk: misses obvious swings in flat markets.
- **Weak** (`≥` / `≤`): equal highs allowed. Risk: produces dense clusters of "swings" on consolidations.

**Decision (v1):** *Strict on both sides*. Equal-extreme bars form **liquidity pools** (handled in concept 10), not swings. This keeps swings sparse and makes structure transitions clean.

## 4. Detection (pseudocode)

```text
input:
    bars: list of Bar(open, high, low, close, ts_ny)   indexed 0..M-1
    N: int (default 1 → 3-bar fractal)

output:
    swings: list of Swing(index, ts_ny, kind ∈ {HIGH, LOW}, price, confirmed_at_index)

for t in N .. M-1-N:
    is_sh = all(bars[t].high > bars[t-k].high and bars[t].high > bars[t+k].high
                for k in 1..N)
    is_sl = all(bars[t].low  < bars[t-k].low  and bars[t].low  < bars[t+k].low
                for k in 1..N)
    if is_sh:
        emit Swing(index=t, kind=HIGH, price=bars[t].high, confirmed_at=t+N)
    if is_sl:
        emit Swing(index=t, kind=LOW,  price=bars[t].low,  confirmed_at=t+N)
```

For streaming mode (live or bar-by-bar backtest), maintain a rolling window of size `2N+1` and emit at the close of bar `t+N`.

## 5. Invalidation

A swing is not "invalidated" — it is a historical fact about the bar at index `t`. What *changes* is its **structural role** (turned into a "broken swing" once a later body close pierces it — see concept 02, BoS).

The only failure mode for the detector itself: insufficient bars (a candidate at `t` with `t < N` or `t > M-1-N` cannot be evaluated).

## 6. Confluence rules

- A swing point gains weight when it coincides with:
  - A higher-timeframe swing (HTF SH inside an LTF SH cluster ⇒ much stronger pivot).
  - A PD Array boundary (an OB or FVG edge that sits on the same price).
  - A round/figure level relative to the instrument (e.g., NQ `100`-point steps).
- A swing loses weight if it sits inside a documented news window (08:30 NY printing range).

## 7. Parameters (configs/default.yaml)

```yaml
structure:
  swing_lookback: 3      # 3 = 3-bar fractal (N=1); also expose N directly:
  swing_half_width_N: 1  # canonical name; swing_lookback retained for back-compat
  swing_strict_inequality: true
```

## 8. Test fixtures (to author in Phase 3)

- `tests/fixtures/swings/sh_3bar_minimal.csv` — 3 bars, middle bar's high strictly greatest ⇒ exactly one SH at index 1.
- `tests/fixtures/swings/sl_3bar_minimal.csv` — symmetric, exactly one SL at index 1.
- `tests/fixtures/swings/sh_5bar_N2.csv` — only confirmed for `N=2`, fails for stricter `N=3`.
- `tests/fixtures/swings/equal_highs_no_swing.csv` — two adjacent bars with equal highs ⇒ no SH under strict mode.
- `tests/fixtures/swings/provisional_swing.csv` — bar `t` that *would* be a swing but `t+N` hasn't closed yet ⇒ provisional, not confirmed.

## 9. Open questions

- **(Q1.a)** Should the bot also expose a "compound swing" (a swing whose neighbours of width 1 are themselves swings of width N=2) for multi-timeframe alignment, or do we cover that via HTF resampling instead? **Default decision in v1: via HTF resampling.**
- **(Q1.b)** For tick-resolution detection on L2-driven mode, what counts as a "bar"? **Default decision in v1: swings only run on resampled OHLCV; L2 ticks never produce swings directly.**

## 10. Cross-references

- Used by [02 — Market Structure](./02_market_structure.md) to compute HH/HL/LH/LL and BoS/ChoCH/MSS.
- Used by [05 — Order Block](./05_order_block.md) to identify "last opposing candle".
- Used by [10 — Liquidity](./10_liquidity.md) where each confirmed swing high anchors BSL and each swing low anchors SSL.
- Used by [11 — Dealing Range / OTE](./11_dealing_range_ote.md) as the endpoints of the active range.
