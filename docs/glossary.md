# Glossary — ICT term → algorithmic equivalent

This glossary maps ICT terminology to the precise data structures and modules in this codebase. Formal specs live in `docs/concepts/` (one per term, populated in Phase 1).

| ICT term | This codebase | Brief |
| -------- | ------------- | ----- |
| IPDA — Interbank Price Delivery Algorithm | implicit assumption | The market behaves as a single price-delivery engine that targets liquidity and inefficiencies on a time schedule. Not a class — it shapes the engine's *gating* logic. |
| PO3 — Power of Three | `signals/setups/po3.py` (Phase 4) | Accumulation → Judas → Distribution. Encoded as a session-level state machine. |
| Killzone | `sessions/killzones.py` (Phase 3) | Time window during which entries are allowed. Defined in `configs/nq.yaml`. |
| Midnight Open | `sessions/midnight_open.py` | The 00:00 NY price; longs must be below it, shorts above. |
| Swing High / Swing Low | `structure/swings.py` | 3-bar fractal: `High[t] > High[t-1] ∧ High[t] > High[t+1]`. |
| BoS — Break of Structure | `structure/market_structure.py` | Body close beyond the last opposing swing in the prevailing trend's direction. |
| ChoCH — Change of Character | `structure/market_structure.py` | Local break against the prevailing trend; weaker than MSS. |
| MSS — Market Structure Shift | `structure/market_structure.py` | ChoCH that also carries displacement and an imbalance. |
| Displacement | `structure/displacement.py` | Body/range and body-vs-ATR ratio above thresholds. |
| FVG — Fair Value Gap | `signals/imbalance/fvg.py` | 3-candle gap; sub-types BISI (bullish) and SIBI (bearish). |
| CE — Consequent Encroachment | inside `fvg.py` | Mathematical midpoint of an FVG; highest-sensitivity coordinate. |
| BPR — Balanced Price Range | `signals/imbalance/bpr.py` | Overlapping BISI ∩ SIBI = rigid level. |
| Volume Imbalance | `signals/imbalance/volume_imbalance.py` | Body-to-body gap between consecutive candles. |
| OB — Order Block | `signals/blocks/order_block.py` | Last opposing candle before a displacement that breaks structure. |
| Mean Threshold (MT) | inside `order_block.py` | Mid-price of an OB; body close beyond invalidates. |
| Breaker Block | `signals/blocks/breaker.py` | A failed OB after a liquidity sweep — reversal structure. |
| Mitigation Block | `signals/blocks/mitigation.py` | Old OB respected on retest — continuation. |
| Rejection Block | `signals/blocks/rejection.py` | Wick of a fast sweep; quick reversal from extremes. |
| PD Array | `signals/` hierarchy + `setups/` selector | Premium/Discount Array. Priority order in `STRATEGY.md`. |
| Dealing Range | `signals/ranges/dealing_range.py` | High/low pair on the reference timeframe; splits Premium/Discount. |
| Premium / Discount / Equilibrium | inside `dealing_range.py` | Above mid / below mid / exactly mid. |
| OTE — Optimal Trade Entry | `signals/ranges/ote.py` | Fibonacci retracement 0.62–0.79 (sweet spot 0.705). |
| BSL / SSL | `signals/liquidity/pools.py` | Buy-Side / Sell-Side Liquidity above highs / below lows. |
| Equal Highs / Equal Lows | `signals/liquidity/equal_levels.py` | Repeated extremes within a tolerance. |
| Liquidity Sweep | `signals/liquidity/sweep.py` | Wick beyond a pool followed by reversal. |
| Inducement | `signals/liquidity/inducement.py` | Small counter-trend pullback engineered to sweep retail stops before continuation. |
| Unicorn Model | `signals/setups/unicorn.py` | Breaker ∩ FVG, ideally inside OTE. |
| Silver Bullet | `signals/setups/silver_bullet.py` | NY AM time-anchored setup, ~10:00–11:00 NY. |
