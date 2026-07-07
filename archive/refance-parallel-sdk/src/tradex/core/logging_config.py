"""Structured logging framework.

Provider-agnostic logging with context injection.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

try:
    import structlog

    HAS_STRUCTLOG = True
except ImportError:
    HAS_STRUCTLOG = False


def setup_logging(
    level: str = "INFO",
    json_output: bool = False,
    provider: str = "",
) -> Any:
    """Configure structured logging for the SDK.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        json_output: If True, output JSON. Otherwise, human-readable.
        provider: Provider name to inject into all log entries.
    """
    if HAS_STRUCTLOG:
        shared_processors = [
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.add_log_level,
        ]

        structlog.configure(
            processors=[
                *shared_processors,
                structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
            ],
            wrapper_class=structlog.stdlib.BoundLogger,
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )

        if provider:
            structlog.contextvars.bind_contextvars(provider=provider)

        # Configure stdlib logging with structlog's ProcessorFormatter
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            structlog.stdlib.ProcessorFormatter(
                processor=structlog.dev.ConsoleRenderer(),
                foreign_pre_chain=shared_processors,
            )
        )
        root_logger = logging.getLogger()
        root_logger.handlers.clear()
        root_logger.addHandler(handler)
        root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    else:
        logging.basicConfig(
            format="%(message)s",
            stream=sys.stdout,
            level=getattr(logging, level.upper(), logging.INFO),
        )

    return logging.getLogger("tradex")


# Auto-configure structlog at import time so loggers work immediately
if HAS_STRUCTLOG:
    try:
        shared_processors = [
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.add_log_level,
        ]

        structlog.configure(
            processors=[
                *shared_processors,
                structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
            ],
            wrapper_class=structlog.stdlib.BoundLogger,
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )

        # Set up the stdlib handler with structlog formatter
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            structlog.stdlib.ProcessorFormatter(
                processor=structlog.dev.ConsoleRenderer(),
                foreign_pre_chain=shared_processors,
            )
        )
        root_logger = logging.getLogger()
        root_logger.handlers.clear()
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.WARNING)  # Default to WARNING for tests
    except Exception:
        pass  # Already configured


class KwargsLogger:
    """Wrapper around stdlib Logger that accepts keyword arguments.

    Converts keyword arguments into key=value pairs appended to the log message.
    This allows call sites using structlog-style kwargs (e.g., logger.error('msg', error=str(e)))
    to work when structlog is not installed.
    """

    def __init__(self, logger: logging.Logger):
        self._logger = logger

    def _format_message(self, args: tuple, kwargs: dict) -> tuple:
        """Format positional args and keyword args into a message."""
        if not kwargs:
            return args
        parts = [str(a) for a in args]
        for k, v in kwargs.items():
            parts.append(f"{k}={v}")
        return (tuple(parts),)

    def debug(self, *args: Any, **kwargs: Any) -> None:
        args = self._format_message(args, kwargs)
        self._logger.debug(*args)

    def info(self, *args: Any, **kwargs: Any) -> None:
        args = self._format_message(args, kwargs)
        self._logger.info(*args)

    def warning(self, *args: Any, **kwargs: Any) -> None:
        args = self._format_message(args, kwargs)
        self._logger.warning(*args)

    def error(self, *args: Any, **kwargs: Any) -> None:
        args = self._format_message(args, kwargs)
        self._logger.error(*args)

    def critical(self, *args: Any, **kwargs: Any) -> None:
        args = self._format_message(args, kwargs)
        self._logger.critical(*args)

    def exception(self, *args: Any, **kwargs: Any) -> None:
        args = self._format_message(args, kwargs)
        self._logger.exception(*args)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._logger, name)


def get_logger(name: str) -> Any:
    """Get a named logger.

    Returns a structlog BoundLogger if structlog is available,
    otherwise returns a KwargsLogger wrapping the stdlib logger.
    """
    if HAS_STRUCTLOG:
        return structlog.get_logger(f"tradex.{name}")
    return KwargsLogger(logging.getLogger(f"tradex.{name}"))


class LoggerMixin:
    """Mixin that provides a logger for any class."""

    @property
    def logger(self) -> Any:
        if HAS_STRUCTLOG:
            return structlog.get_logger(f"tradex.{self.__class__.__name__}")
        return KwargsLogger(logging.getLogger(f"tradex.{self.__class__.__name__}"))
