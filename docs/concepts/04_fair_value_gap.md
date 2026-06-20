# 04 — Fair Value Gap (BISI, SIBI, CE, BPR, Volume Imbalance)

> **Status:** spec v1 — pending sign-off
> **Source:** `docs/research/ict_concepts_research.md` § "Modelado de Desequilibrios de Liquidez"
> **Cross-reference:** [ictindex.io](https://www.ictindex.io/) — queries *"fair value gap"*, *"BISI SIBI"*, *"consequent encroachment"*, *"balanced price range"*
> **Implements:** `src/ict_bot/signals/imbalance/fvg.py`, `bpr.py`, `volume_imbalance.py` (Phase 3)
> **Depends on:** [03 — Displacement](./03_displacement.md)
> **Depended on by:** 02 (MSS), 09 (PD Array hierarchy), 14 (Unicorn)

## 1. Definitions

### 1.1 Fair Value Gap (FVG)

A **three-candle pattern** where the wick of candle `t` and the wick of candle `t+2` fail to overlap, leaving an empty price region traversed only by the middle candle `t+1`. The IPDA tends to rebalance this gap, so it acts as a price magnet.

Two sub-types by direction:

- **BISI (Buy-side Imbalance / Sell-side Inefficiency)** — bullish FVG.
- **SIBI (Sell-side Imbalance / Buy-side Inefficiency)** — bearish FVG.

### 1.2 Consequent Encroachment (CE)

The exact midpoint of the FVG. ICT considers CE the highest-sensitivity coordinate: price reactions often occur there without filling the gap fully.

### 1.3 Balanced Price Range (BPR)

A geometric overlap of a BISI and an SIBI that share price space (one above, one below in time, overlapping in price). Acts as a rigid, fast-rejection zone.

### 1.4 Volume Imbalance (VI)

A *body-to-body* gap (open of bar `t+1` opens away from the close of bar `t` without intersecting wicks bridging them). Weaker than FVG but the same family — IPDA seeks to fill them.

## 2. Notation

| Symbol | Meaning |
| ------ | ------- |
| `H_t, L_t, O_t, C_t` | High, low, open, close of bar `t` |
| `[a, b]` | Closed price interval, `a < b` |
| `CE(g)` | Consequent encroachment of gap `g` |

## 3. Formal definitions

### 3.1 BISI (bullish FVG)

Form across three consecutive bars `(t, t+1, t+2)`:

```
BISI(t)   ⇔   L_{t+2}  >  H_t
```

Gap interval:

```
BISI.range = [ H_t , L_{t+2} ]
CE(BISI)   = H_t + 0.5 × ( L_{t+2} − H_t )
```

Optionally require the middle bar `t+1` to be a displacement bar of `BULL` direction (config `imbalance.fvg.require_displacement = true`).

### 3.2 SIBI (bearish FVG)

```
SIBI(t)   ⇔   H_{t+2}  <  L_t
```

Gap interval:

```
SIBI.range = [ H_{t+2} , L_t ]
CE(SIBI)   = H_{t+2} + 0.5 × ( L_t − H_{t+2} )
```

Same optional displacement requirement on bar `t+1`, direction `BEAR`.

### 3.3 BPR (Balanced Price Range)

Given two FVGs `g_up` (BISI) and `g_dn` (SIBI), with `g_dn` formed after `g_up`:

```
BPR(g_up, g_dn)   ⇔   g_up.range  ∩  g_dn.range   ≠   ∅
BPR.range         =   g_up.range  ∩  g_dn.range
```

Order can be reversed (`g_dn` first, then `g_up`); either ordering produces a BPR.

### 3.4 Volume Imbalance (VI)

```
VI_bull(t)   ⇔   O_{t+1}  >  C_t   AND   C_t == max(O_t, C_t)
VI_bear(t)   ⇔   O_{t+1}  <  C_t   AND   C_t == min(O_t, C_t)
```

(Body-to-body separation with no wick-bridge crossing the gap region.)

VI interval (bull example):

```
VI_bull.range = [ C_t , O_{t+1} ]
```

VIs are weaker than FVGs and used primarily as **confluence boosters**, not standalone entries.

## 4. Detection (pseudocode)

```text
input:
    bars: ordered list of Bar
    require_displacement: bool (default true)
    displacement_dir(bars, t): function → {BULL, BEAR, NONE}  (concept 03)

fvgs = []
for t in 0 .. len(bars)-3:
    # BISI
    if bars[t+2].low > bars[t].high:
        if require_displacement and displacement_dir(bars, t+1) != BULL:
            pass
        else:
            g = FVG(kind=BISI, anchor_t=t, range=[bars[t].high, bars[t+2].low])
            g.ce = midpoint(g.range)
            fvgs.append(g)
    # SIBI
    if bars[t+2].high < bars[t].low:
        if require_displacement and displacement_dir(bars, t+1) != BEAR:
            pass
        else:
            g = FVG(kind=SIBI, anchor_t=t, range=[bars[t+2].high, bars[t].low])
            g.ce = midpoint(g.range)
            fvgs.append(g)

# BPR scan (O(N^2) over open FVGs only)
open_fvgs = [g for g in fvgs if not g.invalidated]
bprs = []
for g1, g2 in pairs(open_fvgs):
    if g1.kind != g2.kind and intervals_intersect(g1.range, g2.range):
        bprs.append(BPR(components=(g1, g2), range=intersection(g1.range, g2.range)))

# Volume Imbalance
vis = []
for t in 0 .. len(bars)-2:
    if bars[t+1].open > bars[t].close and bars[t].close == max(bars[t].open, bars[t].close):
        vis.append(VI(kind=BULL, t=t, range=[bars[t].close, bars[t+1].open]))
    if bars[t+1].open < bars[t].close and bars[t].close == min(bars[t].open, bars[t].close):
        vis.append(VI(kind=BEAR, t=t, range=[bars[t+1].open, bars[t].close]))
```

## 5. Invalidation

| Object | Invalidation condition |
| ------ | --------------------- |
| **BISI** | A later bar's body closes below `CE(BISI)` — wick alone is not enough. The user's research markdown specifies "Invasion of the body beyond CE". |
| **SIBI** | A later bar's body closes above `CE(SIBI)`. |
| **BPR** | Either of the two constituent FVGs is invalidated, **or** a body close traverses the entire BPR range. |
| **VI** | A body close on the opposite side of the gap. |

Invalidated objects move to a `history` registry — they may still be useful for Breaker formation (see concept 06) but no longer count as active PD Arrays.

## 6. Confluence rules

- An FVG that sits inside a higher-timeframe PD Array (an HTF OB, FVG, or Dealing Range OTE zone) is *high-confluence*; outside, *low-confluence*.
- A BPR overrides individual FVGs at the same price (rigid > magnetic).
- An FVG generated by a displacement leg confirmed via L2 `delta_acceleration` (Phase 8) gets the `L2-confirmed` tag.
- Two FVGs of the same direction stacked vertically (no gap between them) act as a "tower" — entry at the upper edge of the lower FVG.

## 7. Parameters (configs/default.yaml)

```yaml
imbalance:
  fvg:
    require_displacement: true
    invalidation: body_close_beyond_ce
    min_gap_ticks: 1                  # at least one tick of gap
  bpr:
    require_overlap: true
    invalidation: any_component_invalidated_or_body_close_traverses
  volume_imbalance:
    enable: true
    min_gap_ticks: 1
```

## 8. Test fixtures

- `tests/fixtures/fvg/bisi_minimal.csv` — three bars where `Low[t+2] > High[t]`, middle bar bullish displacement ⇒ one BISI.
- `tests/fixtures/fvg/sibi_minimal.csv` — symmetric for SIBI.
- `tests/fixtures/fvg/bisi_no_displacement.csv` — gap present but middle bar small body ⇒ no FVG when `require_displacement=true`, FVG when `false`.
- `tests/fixtures/fvg/bisi_invalidated_by_body_below_ce.csv` — BISI followed by a bar whose body closes below the CE ⇒ invalidated.
- `tests/fixtures/fvg/bisi_wick_only_below_ce.csv` — wick punctures CE but body closes back above ⇒ remains valid.
- `tests/fixtures/fvg/bpr_overlap.csv` — BISI and SIBI sharing price overlap ⇒ one BPR with intersection range.
- `tests/fixtures/fvg/vi_bull.csv` — body-to-body bullish gap without wick bridge ⇒ VI.

## 9. Open questions

- **(Q4.a)** Should we also model the "Liquidity Void" (broader concept than FVG, spanning many bars)? **Default v1:** no; treat large-scale voids as concatenations of stacked FVGs/VIs for now.
- **(Q4.b)** When two FVGs of the same direction are nested, do they count as one or two PD Array entries? **Default v1:** two distinct entries; the upper edge of the lower one is the primary entry; the upper edge of the upper one is a secondary target.
- **(Q4.c)** Tick-granularity: should `min_gap_ticks` be enforced on resampled timeframes equally, or scale with TF? **Default v1:** scale with TF — config exposes `min_gap_ticks_by_tf`.

## 10. Cross-references

- Generation depends on [03 — Displacement](./03_displacement.md).
- Consumed by [02 — MSS](./02_market_structure.md) (FVG required on the breaking leg).
- Composed with Breaker in [14 — Unicorn](./14_unicorn_model.md).
- Ranked in [09 — PD Array hierarchy](./09_pd_array_hierarchy.md) at level 5; BPR is level 4/5 effectively.
