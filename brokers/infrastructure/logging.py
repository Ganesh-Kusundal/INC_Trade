"""Structured logging adapter — consistent key=value audit logs.

Provides a lightweight wrapper around the standard ``logging`` module
that enforces structured key=value message patterns for all broker
audit events — order placement, market data fetches, health checks.

Usage::

    from brokers.infrastructure.logging import get_logger

    logger = get_logger(__name__)

    logger.info("order_placed", order_id="ord_123", symbol="RELIANCE")
    # → 2026-07-02T10:30:00Z INFO order_placed order_id=ord_123 symbol=RELIANCE

    logger.warning("rate_limit_hit", endpoint="place_order", retry_ms=500)
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from typing import Any


class StructuredLogger:
    """Logger that emits key=value structured messages.

    Wraps a standard ``logging.Logger`` and formats extra kwargs as
    ``key=value`` pairs in the log message.  Zero external dependencies.
    """

    def __init__(self, name: str, *, level: int = logging.INFO) -> None:
        self._logger = logging.getLogger(name)
        self._logger.setLevel(level)
        self._logger.propagate = False

        if not self._logger.handlers:
            handler = logging.StreamHandler(sys.stderr)
            handler.setFormatter(_StructuredFormatter())
            self._logger.addHandler(handler)

    # ── Logging methods ──────────────────────────────────────────────────

    def debug(self, event: str, **kwargs: Any) -> None:
        self._logger.debug(event, extra={"structured": kwargs})

    def info(self, event: str, **kwargs: Any) -> None:
        self._logger.info(event, extra={"structured": kwargs})

    def warning(self, event: str, **kwargs: Any) -> None:
        self._logger.warning(event, extra={"structured": kwargs})

    def error(self, event: str, **kwargs: Any) -> None:
        self._logger.error(event, extra={"structured": kwargs})

    def critical(self, event: str, **kwargs: Any) -> None:
        self._logger.critical(event, extra={"structured": kwargs})

    def exception(self, event: str, **kwargs: Any) -> None:
        self._logger.exception(event, extra={"structured": kwargs})

    # ── Convenience ──────────────────────────────────────────────────────

    def with_context(self, **context: Any) -> StructuredLogger:
        """Return a child logger with pre-bound context keys.

        The child logger shares the parent's underlying ``logging.Logger``
        but automatically merges the pre-bound *context* into every log call.
        """
        child = StructuredLogger.__new__(StructuredLogger)
        child._logger = self._logger
        for method in ("debug", "info", "warning", "error", "critical", "exception"):
            setattr(child, method, _make_adapter_method(self._logger, method, context))
        return child


def _make_adapter_method(logger: logging.Logger, method: str, context: dict[str, Any]):
    """Create a method that merges context with per-call kwargs."""

    def _log(event: str, **kwargs: Any) -> None:
        merged = {**context, **kwargs}
        getattr(logger, method)(event, extra={"structured": merged})

    return _log


# ── Formatter ─────────────────────────────────────────────────────────────


class _StructuredFormatter(logging.Formatter):
    """Format log records as ``timestamp LEVEL event key=value ...``."""

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()
        base = f"{ts} {record.levelname:<8} {record.getMessage()}"

        structured = getattr(record, "structured", None)
        if structured:
            parts = []
            for k, v in structured.items():
                parts.append(f"{k}={_format_value(v)}")
            if parts:
                base += " " + " ".join(parts)

        if record.exc_info and record.exc_info[1]:
            base += f" error={record.exc_info[1]}"

        return base


def _format_value(value: Any) -> str:
    """Format a value for structured logging output."""
    if value is None:
        return "null"
    if isinstance(value, str):
        # Quote strings with spaces
        return value if " " not in value else f'"{value}"'
    if isinstance(value, float):
        return f"{value:.3f}".rstrip("0").rstrip(".")
    return str(value)


# ── Module-level factory ──────────────────────────────────────────────────


_loggers: dict[str, StructuredLogger] = {}


def get_logger(name: str, *, level: int = logging.INFO) -> StructuredLogger:
    """Get or create a ``StructuredLogger`` for *name*."""
    if name not in _loggers:
        _loggers[name] = StructuredLogger(name, level=level)
    return _loggers[name]
