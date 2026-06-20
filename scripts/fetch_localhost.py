"""CLI: fetch OHLCV 1-minute bars from the local backtest API and cache as parquet.

Usage:
    python scripts/fetch_localhost.py            # uses defaults from .env
    python scripts/fetch_localhost.py --refresh  # ignore cache, re-fetch
"""

from __future__ import annotations

import argparse

from ict_bot.data.loaders.ohlcv_http import fetch_ohlcv_1m
from ict_bot.utils.logging import configure_logging, get_logger


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch OHLCV 1m from localhost backtest API")
    parser.add_argument("--url", default=None, help="HTTP endpoint")
    parser.add_argument("--symbol", default=None, help="Symbol tag for the cache file")
    parser.add_argument("--refresh", action="store_true", help="Re-fetch ignoring cache")
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()

    configure_logging()
    log = get_logger("scripts.fetch_localhost")

    bars = fetch_ohlcv_1m(
        url=args.url,
        symbol=args.symbol,
        use_cache=not args.refresh,
        refresh=args.refresh,
        timeout_s=args.timeout,
    )
    log.info(
        "ohlcv_ready",
        rows=len(bars),
        first=str(bars.first_ts()),
        last=str(bars.last_ts()),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
