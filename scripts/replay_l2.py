"""CLI: load one or more L2 days, cache to parquet, and print a quick summary.

Usage:
    python scripts/replay_l2.py --day 2026-06-17
    python scripts/replay_l2.py --from 2026-06-10 --to 2026-06-17
"""

from __future__ import annotations

import argparse
from datetime import date

from ict_bot.data.loaders.l2_csv import list_available_days, load_day, load_range
from ict_bot.utils.logging import configure_logging, get_logger


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay / cache L2 ticks")
    g = parser.add_mutually_exclusive_group(required=False)
    g.add_argument("--day", type=_parse_date, help="Single day YYYY-MM-DD")
    g.add_argument("--from", dest="start", type=_parse_date, help="Start date")
    parser.add_argument("--to", dest="end", type=_parse_date, help="End date (with --from)")
    parser.add_argument("--list", action="store_true", help="List available days and exit")
    args = parser.parse_args()

    configure_logging()
    log = get_logger("scripts.replay_l2")

    if args.list:
        days = list_available_days()
        log.info("l2_days_available", count=len(days),
                 first=str(days[0]) if days else None,
                 last=str(days[-1]) if days else None)
        for d in days:
            print(d.isoformat())
        return 0

    if args.day:
        ticks = load_day(args.day)
        log.info("l2_day_loaded", day=str(args.day), rows=len(ticks))
        return 0

    if args.start:
        end = args.end or args.start
        ticks = load_range(args.start, end)
        log.info("l2_range_loaded", start=str(args.start), end=str(end), rows=len(ticks))
        return 0

    parser.error("provide --day, --from/--to, or --list")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
