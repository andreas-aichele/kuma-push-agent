"""Logging configuration for kuma-push-agent."""

from __future__ import annotations

import logging
import sys
from datetime import UTC, datetime


class _UTCFormatter(logging.Formatter):
    """Log formatter that emits UTC timestamps in ISO-8601 format."""

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:  # noqa: N802
        dt = datetime.fromtimestamp(record.created, tz=UTC)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def setup_logging(level: str = "INFO") -> None:
    """Configure root logger with UTC timestamps output to stdout."""
    formatter = _UTCFormatter(fmt="%(asctime)s %(levelname)s %(name)s %(message)s")
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.handlers.clear()
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger."""
    return logging.getLogger(name)
