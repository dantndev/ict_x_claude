"""Structured logging via structlog.

Usage:
    from ict_bot.utils.logging import get_logger
    log = get_logger(__name__)
    log.info("loaded_bars", count=len(bars), tf="1m")
"""

from __future__ import annotations

import logging
import sys
from typing import Any, cast

import structlog


def configure_logging(level: str = "INFO", *, json_output: bool = False) -> None:
    """Configure structlog + stdlib logging once at process start."""
    log_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    if json_output:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=True))

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a bound logger for the given module name."""
    return cast("structlog.stdlib.BoundLogger", structlog.get_logger(name))
