"""Structured logging (structlog): key-value events that are easy to grep and parse."""

from __future__ import annotations

import logging
from typing import Any

import structlog

_configured = False


def configure_logging(level: str = "INFO") -> None:
    """Configure structlog once for the process."""
    global _configured
    if _configured:
        return
    logging.basicConfig(format="%(message)s", level=level)
    for noisy in ("httpx", "httpcore", "openai", "urllib3"):  # per-request INFO lines
        logging.getLogger(noisy).setLevel(logging.WARNING)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="%H:%M:%S"),
            structlog.dev.ConsoleRenderer(colors=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level)),
    )
    _configured = True


def get_logger(name: str) -> Any:
    """Return a structlog logger bound to a module name."""
    return structlog.get_logger(name)
