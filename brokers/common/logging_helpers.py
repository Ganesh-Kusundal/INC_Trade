"""Shared logging helpers — eliminates duplication across common/ modules.

These helpers wrap standard ``logging`` to safely pass ``**extra`` kwargs.
Modules that need structured logging should prefer ``get_logger()`` from
``brokers.infrastructure.logging`` instead.
"""

from __future__ import annotations

import logging
from typing import Any

_logger = logging.getLogger(__name__)


def log_info(msg: str, **extra: Any) -> None:
    """Log at INFO level with optional extra context."""
    try:
        _logger.info(msg, extra=extra)
    except (TypeError, KeyError):
        _logger.info(f"{msg} {extra}")


def log_warning(msg: str, **extra: Any) -> None:
    """Log at WARNING level with optional extra context."""
    try:
        _logger.warning(msg, extra=extra)
    except (TypeError, KeyError):
        _logger.warning(f"{msg} {extra}")


def log_debug(msg: str, **extra: Any) -> None:
    """Log at DEBUG level with optional extra context."""
    try:
        _logger.debug(msg, extra=extra)
    except (TypeError, KeyError):
        _logger.debug(f"{msg} {extra}")


def log_error(msg: str, **extra: Any) -> None:
    """Log at ERROR level with optional extra context."""
    try:
        _logger.error(msg, extra=extra)
    except (TypeError, KeyError):
        _logger.error(f"{msg} {extra}")


__all__ = ["log_info", "log_warning", "log_debug", "log_error"]
