# 10 — Liquidity (BSL, SSL, Equal Highs/Lows, Sweep, Inducement)

> **Status:** spec v1 — pending sign-off
> **Source:** `docs/research/ict_concepts_research.md` § "Protocolos Temporales de Ejecución y Gestión de Liquidez"
> **Cross-reference:** [ictindex.io](https://www.ictindex.io/) — queries *"buy-side liquidity", "sell-side liquidity", "liquidity sweep", "inducement"*
> **Implements:** `src/ict_bot/signals/liquidity/pools.py`, `equal_levels.py`, `sweep.py`, `inducement.py` (Phase 3)
> **Depends on:** [01 — Swing High/Low](./01_swing_points.md)
> **Depended on by:** 02 (MSS), 06 (Breaker), 08 (Rejection), 14

## 1. Definitions

### 1.1 Liquidity pools

| Term | Where | What sits there |
| ---- | ----- | --------------- |
| **Buy-Side Liquidity (BSL)** | Above swing highs and equal-highs clusters | Buy-stops: stop-loss orders of short positions + breakout-buy orders |
| **Sell-Side Liquidity (SSL)** | Below swing lows and equal-lows clusters | Sell-stops: stop-loss orders of long positions + breakout-sell orders |

ICT assumes the IPDA targets these pools to fill institutional orders. Long entries are favored AFTER an SSL sweep; short entries AFTER a BSL sweep.

### 1.2 Equal Highs / Equal Lows

A cluster of swing extremes whose prices match to within a tolerance. Equal-extremes act as **magnets** because they advertise concentrated stops.

### 1.3 Liquidity Sweep

A wick that puncts a documented liquidity pool followed by a reversal **without** a body close beyond the pool. Distinct from a Break of Structure (BoS = body close beyond).

### 1.4 Inducement

A small counter-trend pullback engineered after a structural move, designed to sweep retail breakout stops before continuation. Mathematically a sweep at a **minor** local extreme (a swing on a *lower* timeframe than the prevailing trend's reference TF).

## 2. Notation

| Symbol | Meaning |
| ------ | ------- |
| `pool`            | A liquidity pool object: `kind ∈ {BSL, SSL}`, `price`, `anchor_swings: list[Swing]`, `created_at` |
| `tol_ticks`       | Tolerance for clustering equal extremes (config) |
| `Sweep(side, t, depth)` | Sweep event: side `BSL/SSL`, bar `t`, depth = how far beyond the pool the wick reached |

## 3. Formal definitions

### 3.1 Pool from a single swing

Every confirmed swing high (concept 01) creates a BSL pool **at** its price; every swing low creates an SSL pool. Pool lifespan: until invalidated (see §5).

```
For each confirmed SH at index t_s with price p:
    register Pool(kind=BSL, price=p, anchor_swings=[SH_t_s], created_at=t_s + N)
For each confirmed SL at index t_s with price p:
    register Pool(kind=SSL, price=p, anchor_swings=[SL_t_s], created_at=t_s + N)
```

### 3.2 Equal-extremes clustering (super-pool)

Two same-kind swings `s_i`, `s_j` are **equal** if:

```
|s_i.price - s_j.price|  ≤  tol_ticks × tick_size
```

A cluster is a maximal set of pairwise-equal swings. Each cluster collapses into a single pool whose `anchor_swings` is the list of members and whose `price` is the **maximum** for BSL or **minimum** for SSL (the actual stop trigger level).

A cluster pool inherits a higher *priority* score than a single-swing pool — the IPDA strongly favors visited equal-extreme regions.

### 3.3 Sweep detection

A bar `t` produces a sweep against a pool `P` when:

```
For P.kind == BSL:
    Sweep_BSL(t, P)  ⇔   H_t  >  P.price   AND   max(O_t, C_t)  ≤  P.price
For P.kind == SSL:
    Sweep_SSL(t, P)  ⇔   L_t  <  P.price   AND   min(O_t, C_t)  ≥  P.price
```

Depth:

```
depth_BSL = H_t - P.price
depth_SSL = P.price - L_t
```

A body close beyond the pool is **not** a sweep — it is a Break of Structure / pool consumption (the pool is "taken" rather than "swept and rejected"). The engine distinguishes both events:

```
ConsumePool_BSL(t, P)  ⇔  Close_t  >  P.price       (pool transitions to invalidated)
ConsumePool_SSL(t, P)  ⇔  Close_t  <  P.price
```

### 3.4 Inducement

An **Inducement** is a sweep at a **minor** local extreme — defined as a swing of width `N` on a lower timeframe than the prevailing-trend reference TF (config `liquidity.inducement.minor_tf` default `1m` when bias is `15m+`).

```
Inducement(t)  ⇔  Sweep(t, P_minor)   for any minor-TF pool P_minor
                  AND  prevailing trend on reference TF unchanged through t
```

Inducements are used by setups (Phase 4) as triggers to enter on the *continuation* of the prevailing trend after the sweep completes.

## 4. Detection (pseudocode)

```text
input:
    bars
    swings (per timeframe; concept 01 over each resampled TF)
    config: { tol_ticks, tick_size, minor_tf, ... }

pools = []

# Build single-swing pools per TF
for tf, swings_tf in swings.items():
    for s in swings_tf:
        pool_kind = BSL if s.kind == HIGH else SSL
        pools.append(Pool(kind=pool_kind, price=s.price, tf=tf,
                          anchor_swings=[s], created_at=s.confirmed_at))

# Cluster equal extremes per TF and per kind
for tf in timeframes:
    for kind in [BSL, SSL]:
        same_kind_swings = [s for s in swings[tf]
                            if (s.kind == HIGH) == (kind == BSL)]
        clusters = cluster_by_price(same_kind_swings, tol_ticks * tick_size)
        for c in clusters:
            if len(c) >= 2:
                price = max(s.price for s in c) if kind == BSL \
                        else min(s.price for s in c)
                pools.append(Pool(kind=kind, price=price, tf=tf,
                                  anchor_swings=list(c), is_cluster=True,
                                  created_at=max(s.confirmed_at for s in c)))

# Sweep scan
sweeps = []
for t in range(len(bars)):
    for P in active_pools_at(t):
        if P.kind == BSL and bars[t].high > P.price and \
           max(bars[t].open, bars[t].close) <= P.price:
            sweeps.append(Sweep(side=BSL, t=t, depth=bars[t].high - P.price, pool=P))
        elif P.kind == SSL and bars[t].low < P.price and \
             min(bars[t].open, bars[t].close) >= P.price:
            sweeps.append(Sweep(side=SSL, t=t, depth=P.price - bars[t].low, pool=P))

# Inducement scan (sweeps tagged as inducement when on minor-TF pools and trend unchanged)
inducements = [s for s in sweeps
               if s.pool.tf == config.minor_tf and trend_unchanged_through(s.t)]
```

## 5. Invalidation

| Event | Effect on pool |
| ----- | -------------- |
| Sweep (wick only) | Pool **persists** but marked `swept_count += 1`. Some ICT teachers consider a pool exhausted after one sweep; v1 keeps it active until a body close consumes it. |
| Body close beyond pool (ConsumePool) | Pool **invalidated** and moved to history. |
| Pool age exceeds `max_age_bars` on a given TF | Pool tagged `stale`; eligible for pruning. Default: no auto-pruning in v1, but the tag is set. |

## 6. Confluence rules

- Cluster pools dominate single-swing pools at the same price.
- Pools at HTF (D/H4) extremes dominate LTF pools.
- A pool that lines up with the previous session's high/low is amplified.
- A pool that has been swept already (`swept_count ≥ 1`) is downgraded — the easy stops are gone.

## 7. Parameters (configs/default.yaml)

```yaml
liquidity:
  equal_levels:
    tolerance_ticks: 2
    min_cluster_size: 2
  sweep:
    wick_only_required: true   # body close = consumption, not sweep
    min_depth_ticks: 1
  inducement:
    minor_tf: "1m"
    enable: true
  pools:
    max_age_bars: null         # no auto-pruning by default
    htf_priority_boost: 1.5    # multiplier on confluence score
```

## 8. Test fixtures

- `tests/fixtures/liquidity/single_swing_pool.csv` — one swing high ⇒ one BSL pool at its price.
- `tests/fixtures/liquidity/equal_highs_cluster.csv` — three swing highs within 2 ticks ⇒ one cluster pool, three anchor swings.
- `tests/fixtures/liquidity/sweep_wick_only.csv` — bar wicks above BSL pool, body closes below ⇒ Sweep event; pool persists with `swept_count=1`.
- `tests/fixtures/liquidity/consume_body_close.csv` — bar body closes above BSL pool ⇒ ConsumePool event; pool invalidated.
- `tests/fixtures/liquidity/inducement_minor_tf.csv` — bull trend on 15m, 1m sweep of a minor SSL during pullback ⇒ Inducement tag.

## 9. Open questions

- **(Q10.a)** Should equal-extremes clustering use a price tolerance or a percentage of ATR? **Default v1:** tick-based tolerance — predictable and configurable.
- **(Q10.b)** Should the engine track `pending_pool_in_extension` (a pool that doesn't exist yet but will form if the next swing extends to a target price)? **Default v1:** no — only confirmed pools.
- **(Q10.c)** "Stop run vs sweep" — some ICT teachers distinguish a fast wick (stop run) from a multi-bar liquidity raid (sweep proper). **Default v1:** treat both as Sweep with a `duration_bars` field.

## 10. Cross-references

- Anchored by [01 — Swing H/L](./01_swing_points.md).
- Sweeps required by [02 — MSS](./02_market_structure.md) and [06 — Breaker](./06_breaker_block.md).
- Sweeps required by [08 — Rejection](./08_rejection_block.md).
- Inducement consumed by setups in Phase 4 (continuation entries after sweep).
