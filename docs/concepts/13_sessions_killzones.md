# 13 — Sessions, Killzones, Midnight Open

> **Status:** spec v1 — pending sign-off
> **Source:** `docs/research/ict_concepts_research.md` § "Protocolos Temporales de Ejecución y Gestión de Liquidez"
> **Cross-reference:** [ictindex.io](https://www.ictindex.io/) — queries *"killzone", "Silver Bullet", "Midnight Open"*
> **Implements:** `src/ict_bot/sessions/{killzones,midnight_open,sessions}.py` (Phase 3)
> **Depends on:** —
> **Depended on by:** every Phase-4 setup, the backtest engine (entry gating, hard-flatten)

## 1. Definitions

All times in **`America/New_York`**. Source-of-truth schedule (copied from the user's research markdown):

| Window (NY) | Identifier | What the bot does |
| ----------- | ---------- | ----------------- |
| `00:00` (single instant) | **Midnight Open** | Record `mid_open` price; arms the bias filter (longs below, shorts above). |
| `02:00 – 05:00` | **London Killzone** | Eligible for new entries; primary venue for daily manipulation/sweep. |
| `07:00 – 10:00` | **NY AM Killzone** | Eligible for new entries; highest expected-value window. |
| `08:30 – 08:35` | **NY Open (news block)** | New entries DISABLED for 5 min; PD Arrays formed before are vulnerable. |
| `10:00 – 11:00` | **Silver Bullet AM** | Sub-window of NY AM; setup tag attached, no special gating beyond NY AM. |
| `12:00 – 13:00` | **NY Lunch** | Engine DISABLED for new entries (low volume). |
| `13:30 – 16:00` | **NY PM Killzone** (Afternoon Algorithm) | Eligible for continuation entries on retest of AM PD Arrays. |
| `14:00 – 15:00` | **Silver Bullet PM** | Sub-window of NY PM; tag-only. |
| `16:30` | **Force Flatten** | All intraday positions closed; all pending orders cancelled. |

Outside the listed eligible windows, the engine is in `IDLE` state: no new orders, but existing positions are managed per their SL/TP rules until 16:30.

## 2. Notation

| Symbol | Meaning |
| ------ | ------- |
| `now_ny(t)` | Local time-of-day on NY clock at bar `t` |
| `mid_open(d)` | Midnight Open price for trading day `d` (the open of the bar whose `ts_ny.time() == 00:00`) |
| `kz_active(t)` | Boolean: is bar `t` inside any *trading-eligible* killzone? |
| `news_block(t)` | Boolean: is bar `t` inside the 08:30 NY news window? |
| `force_flat(t)` | Boolean: bar `t` triggers global flatten |

## 3. Formal definitions

### 3.1 Eligibility

```
kz_active(t)  =  (02:00 ≤ now_ny(t) ≤ 05:00)
              OR (07:00 ≤ now_ny(t) ≤ 10:00)
              OR (13:30 ≤ now_ny(t) ≤ 16:00)

news_block(t) =  (08:30 ≤ now_ny(t) < 08:35)

force_flat(t) =  (now_ny(t) == 16:30)
```

Final entry gate:

```
new_entries_allowed(t)  =  kz_active(t)  AND  NOT news_block(t)  AND  NOT lunch(t)
```

where

```
lunch(t)  =  (12:00 ≤ now_ny(t) < 13:00)
```

### 3.2 Midnight Open

```
mid_open(d)  =  Open of bar b  where b.ts_ny.date() == d  AND  b.ts_ny.time() == 00:00
```

For futures (24/5), the 00:00 NY bar always exists on a trading day. For instruments that don't trade at midnight, fall back to the first available bar after 00:00 NY and tag `synthetic_mid_open=true` in audit. NQ does trade at 00:00, so no fallback in V1.

Bias filter (universal):

```
LongAllowed(t)   ⇔  current_price(t)  <  mid_open(d(t))
ShortAllowed(t)  ⇔  current_price(t)  >  mid_open(d(t))
```

(Config `risk.midnight_open_filter: true` enforces this.)

### 3.3 Silver Bullet windows

Tags only; do not change gating beyond what the parent killzone already enforces.

```
silver_bullet_am(t)  =  (10:00 ≤ now_ny(t) < 11:00)   AND  kz_active(t)
silver_bullet_pm(t)  =  (14:00 ≤ now_ny(t) < 15:00)   AND  kz_active(t)
```

A Setup of class `SilverBullet` (Phase 4) only ever fires when the corresponding tag is true.

### 3.4 Macros (optional, advanced)

ICT also references "macros" — 15-to-20-minute high-probability windows nested within killzones (e.g., 09:50–10:10, 10:50–11:10). These are not part of V1; the schedule above is the gating layer.

## 4. Detection (pseudocode)

```text
input:
    bar with ts_ny

def now_ny(bar):
    return bar.ts_ny.time()      # already localized

def kz_active(bar):
    t = now_ny(bar)
    return (time(2,0)  <= t <= time(5,0))   or \
           (time(7,0)  <= t <= time(10,0))  or \
           (time(13,30)<= t <= time(16,0))

def news_block(bar):
    t = now_ny(bar)
    return time(8,30) <= t < time(8,35)

def lunch(bar):
    t = now_ny(bar)
    return time(12,0) <= t < time(13,0)

def force_flat(bar):
    t = now_ny(bar)
    return t == time(16,30)

def new_entries_allowed(bar):
    return kz_active(bar) and not news_block(bar) and not lunch(bar)

def silver_bullet_am(bar):
    t = now_ny(bar)
    return time(10,0) <= t < time(11,0) and kz_active(bar)

def silver_bullet_pm(bar):
    t = now_ny(bar)
    return time(14,0) <= t < time(15,0) and kz_active(bar)

def midnight_open_for(date):
    # cached lookup; computed once per session by the data layer
    return MID_OPEN_CACHE[date]
```

## 5. Invalidation

- **Killzones, news block, lunch, force-flat** are deterministic functions of time; they don't get invalidated, they just gate behavior.
- **Midnight Open** for day `d` is fixed at the 00:00 NY bar; never recomputed mid-day.
- On a half-day session (CME early close), the `force_flat` time shifts to **30 minutes before scheduled close**. V1 uses a per-date override in `configs/`; default 16:30 otherwise.

## 6. Confluence rules

- A setup that fires **inside a killzone** has full weight.
- A setup that fires **inside Silver Bullet** sub-windows gets a `+1` to the confluence score.
- A setup that crosses **into** the news block (08:30) has its entries cancelled regardless of state.
- A setup with target inside lunch (12:00–13:00) keeps its TP/SL active; only *new* entries are blocked.

## 7. Parameters (configs/default.yaml)

Defaults already live in `configs/default.yaml` under `sessions:`. Repeating here for traceability:

```yaml
sessions:
  midnight_open: "00:00"
  london_kz:      { start: "02:00",  end: "05:00",  trade: true  }
  ny_am_kz:       { start: "07:00",  end: "10:00",  trade: true  }
  ny_open:        { start: "08:30",  end: "08:35",  trade: false }   # news block
  ny_lunch:       { start: "12:00",  end: "13:00",  trade: false }
  ny_pm_kz:       { start: "13:30",  end: "16:00",  trade: true  }
  force_flat_at:  "16:30"
  silver_bullet_am: { start: "10:00", end: "11:00" }
  silver_bullet_pm: { start: "14:00", end: "15:00" }
half_day_overrides:
  # date: time_to_flatten
  # "2026-07-03": "13:00"
```

## 8. Test fixtures

- `tests/fixtures/sessions/london_kz_active.csv` — bars at 02:30 NY ⇒ `kz_active = true`.
- `tests/fixtures/sessions/ny_open_blocked.csv` — bar at 08:31 NY ⇒ `news_block = true`, `new_entries_allowed = false`.
- `tests/fixtures/sessions/lunch_disabled.csv` — bar at 12:30 NY ⇒ `new_entries_allowed = false`.
- `tests/fixtures/sessions/midnight_open_present.csv` — series containing a 00:00 NY bar ⇒ `mid_open` equals that bar's open.
- `tests/fixtures/sessions/force_flat_at_1630.csv` — bar at 16:30 NY ⇒ `force_flat = true`.
- `tests/fixtures/sessions/half_day_override.csv` — date in `half_day_overrides` ⇒ `force_flat` shifts.

## 9. Open questions

- **(Q13.a)** End-of-killzone is inclusive (`<=`) or exclusive (`<`)? Research markdown is mixed. **Default v1:** inclusive (`<=`) on the *end* of trading-eligible windows; exclusive (`<`) on news-block end (so 08:35 onward is trading-eligible again).
- **(Q13.b)** Should the engine define a *premarket Asia killzone* (20:00–00:00 NY) for futures? Research markdown lists it as untraded; v1 leaves it as `IDLE`. Reconsider after seeing distribution of trades in backtest.
- **(Q13.c)** DST transitions — Polars/`zoneinfo` handle these; tests must include a DST-shift week to verify killzone boundaries don't drift.

## 10. Cross-references

- Universal gating layer for every Phase-4 setup.
- Source of `mid_open` used by [12 — PO3](./12_power_of_three.md) and the global bias filter.
- Force-flatten rule enforced by the [Phase 5 backtest engine](../../ROADMAP.md).
