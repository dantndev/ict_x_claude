# Concept: <NAME>

> Source of truth: [ictindex.io](https://www.ictindex.io/) — query for `<concept>`. Cross-reference: `docs/research/ict_concepts_research.md` § <section>.

## 1. Definition (textual)

<Plain-language description as ICT teaches it.>

## 2. Formal definition (math)

<Notation, formulas. Be unambiguous; this is what code must compile to.>

## 3. Detection (pseudocode)

```text
input:  Bars b[0..N-1]  (already in America/New_York)
output: list of <ConceptEvent>

for t in 1..N-2:
    if <condition>:
        emit ConceptEvent(t, ...)
```

## 4. Invalidation rules

- <Condition under which the concept is destroyed and removed from active state.>
- <Wick vs body distinction if relevant.>

## 5. Confluence rules

- <When this concept gains/loses weight in a setup.>
- <Higher-timeframe context requirement, if any.>

## 6. Test fixtures (to author)

- `tests/fixtures/<concept>_positive.csv` — minimal candles where the concept must be detected.
- `tests/fixtures/<concept>_negative.csv` — minimal candles where it must NOT trigger.
- `tests/fixtures/<concept>_invalidation.csv` — sequence that creates then invalidates the concept.

## 7. Open questions

- <Items the user must rule on before implementation.>
