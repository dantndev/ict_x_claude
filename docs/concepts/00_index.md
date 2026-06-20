# ICT Concept Catalog — Phase 1

Each file in this folder is a formal specification of one ICT primitive. The spec is the **single source of truth** for the corresponding detector in `src/`. No detector is implemented until its spec is signed off.

Authoring order respects logical dependencies — later concepts reference earlier ones.

| # | Concept | Doc | Implements |
| - | ------- | --- | ---------- |
| 01 | Swing High / Swing Low | [01_swing_points.md](./01_swing_points.md) | `structure/swings.py` |
| 02 | Market Structure (HH/HL/LH/LL), BoS, ChoCH, MSS | [02_market_structure.md](./02_market_structure.md) | `structure/market_structure.py` |
| 03 | Displacement | [03_displacement.md](./03_displacement.md) | `structure/displacement.py` |
| 04 | Fair Value Gap — BISI, SIBI, CE, BPR, Volume Imbalance | [04_fair_value_gap.md](./04_fair_value_gap.md) | `signals/imbalance/fvg.py` + `bpr.py` + `volume_imbalance.py` |
| 05 | Order Block + Mean Threshold | [05_order_block.md](./05_order_block.md) | `signals/blocks/order_block.py` |
| 06 | Breaker Block | [06_breaker_block.md](./06_breaker_block.md) | `signals/blocks/breaker.py` |
| 07 | Mitigation Block | [07_mitigation_block.md](./07_mitigation_block.md) | `signals/blocks/mitigation.py` |
| 08 | Rejection Block | [08_rejection_block.md](./08_rejection_block.md) | `signals/blocks/rejection.py` |
| 09 | PD Array hierarchy & invalidation | [09_pd_array_hierarchy.md](./09_pd_array_hierarchy.md) | `signals/__init__.py` selector |
| 10 | Liquidity — BSL/SSL, equal H/L, sweep, inducement | [10_liquidity.md](./10_liquidity.md) | `signals/liquidity/*.py` |
| 11 | Dealing Range + Premium/Discount + OTE | [11_dealing_range_ote.md](./11_dealing_range_ote.md) | `signals/ranges/*.py` |
| 12 | Power of Three (PO3) | [12_power_of_three.md](./12_power_of_three.md) | `signals/setups/po3.py` |
| 13 | Killzones + Midnight Open + sessions | [13_sessions_killzones.md](./13_sessions_killzones.md) | `sessions/*.py` |
| 14 | Unicorn Model (composition) | [14_unicorn_model.md](./14_unicorn_model.md) | `signals/setups/unicorn.py` |

## Spec template

Every concept file follows the same skeleton — see [_template.md](./_template.md).

## Source-of-truth policy

- **Primary:** `docs/research/ict_concepts_research.md` (authored from canonical ICT material).
- **Cross-reference:** [ictindex.io](https://www.ictindex.io/) — query the term to validate; record disagreements in the doc's "Open questions" section.
- **Forbidden:** Reddit, random YouTube videos, blog posts that aren't cited in the research markdown.

## Sign-off log

| # | Concept | Signed off (Y/N) | Date | Notes |
| - | ------- | ---------------- | ---- | ----- |
| 01 | Swing High/Low | ⏳ | — | — |
| 02 | Market Structure | ⏳ | — | — |
| 03 | Displacement | ⏳ | — | — |
| 04 | FVG family | ⏳ | — | — |
| 05 | Order Block | ⏳ | — | — |
| 06 | Breaker | ⏳ | — | — |
| 07 | Mitigation | ⏳ | — | — |
| 08 | Rejection | ⏳ | — | — |
| 09 | PD Array hierarchy | ⏳ | — | — |
| 10 | Liquidity | ⏳ | — | — |
| 11 | Dealing Range / OTE | ⏳ | — | — |
| 12 | PO3 | ⏳ | — | — |
| 13 | Sessions / Killzones | ⏳ | — | — |
| 14 | Unicorn Model | ⏳ | — | — |
