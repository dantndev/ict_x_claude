# Operating guide — daily bot ops

Practical day-by-day instructions for running the bot live on the Quantower
+ Lucid bridges. Read this once; everything else is mechanical.

---

## Prerequisites

1. **Quantower running** with both internal bridges active:
   - DOM2 feed at `http://localhost:8080/dom2`
   - Lucid executor at `http://localhost:6001`
2. **`.env` filled** at the repo root with `TELEGRAM_TOKEN` and `TELEGRAM_CHAT_ID`
   (already there for this account).
3. **venv installed**: `pip install -e ".[dev,viz]"` from the repo root.

To verify everything is reachable:

```powershell
.\.venv\Scripts\activate
python -c "from ict_bot.execution.quantower import DOM2Client, LucidExecutor; d=DOM2Client(); s=d.leer(); print('DOM2 OK' if s else 'DOM2 closed/no quotes'); e=LucidExecutor(); print('LUCID:', e.inicializar())"
```

---

## How to start the bot

### Option 1 — From the VSCode UI (recommended)

The repo ships `.vscode/launch.json` with five ready entries. Press **F5**
and pick one:

| Entry | Use |
| ----- | --- |
| **Bot — Dry-run** | Safe. Connects to both bridges, runs the loop, but every order is fake. Best for the first run of the day to confirm wiring. |
| **Bot — LIVE ⚠** | Real orders. Single process. If it crashes you have to restart manually. |
| **Bot — Supervised LIVE ⚠** | Real orders **wrapped by the supervisor**. The Telegram `/restart` command restarts automatically. Crashes are retried up to 5 times in 10 min. This is the right mode for production. |
| **Backtest CME** | Reproduce the production-cell backtest over the long CSV. |
| **Walk-forward CME** | Reproduce the OOS validation that justifies the production config. |

### Option 2 — From the terminal

Open VSCode's integrated terminal (Ctrl-`) in the repo root:

```powershell
# activate venv once per terminal session
.\.venv\Scripts\activate

# Dry-run for an hour
python scripts/run_live.py --dry-run --max-runtime-sec 3600

# REAL — with supervisor (recommended)
python scripts/supervisor.py --confirm LIVE

# REAL — single process (no auto-restart)
python scripts/run_live.py --confirm LIVE
```

### Option 3 — Background (no terminal needed)

For an unattended overnight run, on Windows you can use `start /B` or
schedule via Task Scheduler pointing at `pythonw scripts/supervisor.py
--confirm LIVE`. Logs go to console only — for persistent logs add a
redirect: `> logs\bot.log 2>&1`.

---

## What the bot does during a day

With the current `configs/lucid_propfirm.yaml`:

- **00:00 NY** — captures Midnight Open price (bias filter reference).
- **02:00–10:00 NY** — silent. The bot polls the feed, builds bars, runs
  detectors, and writes to the shadow log, but `allowed_windows` only
  authorize Silver Bullet, so no orders go out.
- **10:00–11:00 NY (Silver Bullet AM)** — first trading window. 0–2 orders.
- **11:00–14:00 NY** — silent again.
- **14:00–15:00 NY (Silver Bullet PM)** — second window. 0–2 orders.
- **15:00–16:30 NY** — silent.
- **16:30 NY** — **force flatten** any open position; cancel any pending.
- After 16:30 — the loop keeps running but takes no entries until tomorrow.

**Heartbeat** every 60 s in the log (price, open positions, paused/kill
state). **Telegram alert** on every order sent, on every position close,
and on every kill-switch trip.

---

## Telegram remote control

When the bot starts, it registers a command menu in your chat (the `/`
button shows the clickable list). All commands are restricted to the
authorized `TELEGRAM_CHAT_ID` — anyone else sending the same commands is
ignored.

| Command | Effect |
| ------- | ------ |
| `/status` | Reports paused state, kill switch, open positions, equity. |
| `/pause` | Stop taking NEW entries. Existing positions keep their SL/TP. |
| `/resume` | Re-enable entries. |
| `/flatten` | Close all open positions IMMEDIATELY via `broker.flatten_all()`. |
| `/stop` | Clean shutdown — loop exits with code 0. Supervisor does NOT relaunch. |
| `/restart` | Flatten + exit with code 42. Supervisor RELAUNCHES automatically. |
| `/help` | Same as the menu. |

**Notifications you'll receive** (one Telegram message per event):

- `[START]` when the bot launches
- `[STOP]` when the loop ends or `/stop` is received
- `[TRADE]` every time an order is submitted (with setup + side + qty)
- `[CERRADO]` when a position closes (TP/SL/flatten)
- `[KILLSWITCH]` if the kill switch trips
- `[ERROR]` on any uncaught loop exception
- `[WARN]` if the feed goes silent for > 60 s
- `[CMD OK]`, `[PAUSE]`, `[RESUME]`, `[FLATTEN]` echoes after each remote command

---

## Supervisor — auto-restart explained

`scripts/supervisor.py` spawns `run_live.py` as a child process and watches
its exit code:

- **0** (clean stop) → supervisor exits too.
- **42** (Telegram `/restart`) → relaunch after 3 s cooldown.
- **Anything else** (crash) → relaunch after 3 s, up to 5 times per 10 min.
  Past that budget, supervisor halts to avoid an infinite restart loop.

Forwards `SIGINT` (Ctrl-C) to the child so a manual stop works too.

This replaces the ad-hoc "exit 42 + wrapper bat" pattern from the previous
bot with one Python process that's testable and portable across machines.

---

## What to expect on a typical Monday open

```
09:00 NY  : open VSCode, F5 → "Bot — Supervised LIVE ⚠"
09:00 NY  : Telegram receives [START]
09:00–09:55 NY: heartbeat logs only, bot is sleeping (outside allowed windows)
09:55 NY  : I check Telegram /status to confirm everything alive
10:00 NY  : Silver Bullet AM opens
10:??–10:?? NY: at most 1-2 [TRADE] messages, immediately followed by [CERRADO] on TP/SL
11:00 NY  : window closes; bot silent for 3 hours
13:55 NY  : /status sanity check again
14:00 NY  : Silver Bullet PM opens
14:??–14:?? NY: 0-2 more trades
15:00 NY  : silent
16:30 NY  : force flatten (whether or not there's an open position)
17:00 NY  : I can leave the bot running, or send /stop to shut it down for the day
```

If anything looks wrong: `/pause` first to stop new entries while you
investigate, then `/flatten` if you want to be flat, then `/stop` if you
want to kill the bot cleanly.

---

## Where to look when something fails

| Symptom | First place to check |
| ------- | -------------------- |
| Bot silent during a window | `/status` → if `paused=True`, send `/resume`. If `kill_tripped=True`, the killswitch went off (see next row). |
| Killswitch tripped | Telegram `[KILLSWITCH]` message tells you the reason (`daily_loss`, `streak`, `manual`). To rearm: `/restart`. |
| No orders even with valid signal | Check `logs/shadow/<today>.csv` → the `skip_reason` column tells you which gate blocked (`outside_allowed_window` / `mid_open_filter_long` / `limits_lock` / `sizing_zero`). |
| Feed alerts (`[WARN]`) | Quantower probably froze. Restart Quantower; the supervised bot will retry the feed automatically. |
| Bot crashes repeatedly | Supervisor stops after 5 crashes in 10 min and writes the reason to stderr. Read the last child output before restarting. |

---

## Shadow log — using it for analysis

`logs/shadow/<YYYY-MM-DD>.csv` accumulates **every detected signal**, even
ones that didn't execute. Columns include `in_mode_A`, `in_mode_B`,
`in_mode_C` so you can do queries like:

```python
import polars as pl
df = pl.read_csv("logs/shadow/2026-07-01.csv")
# What would mode C have done today?
df.filter(pl.col("in_mode_C") == 1).group_by("setup").agg(
    pl.len().alias("n"), pl.col("executed").sum().alias("executed")
)
```

After a few weeks of accumulated shadow data, you can decide whether to
switch from mode B to C based on real numbers — not backtest.
