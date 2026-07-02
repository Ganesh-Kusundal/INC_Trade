"""Centralized logging configuration with structured logging support.

Provides a single, consistent logging setup for the entire TradeXV2 platform.
Supports structured JSON logging for production and human-readable output for
development.

Token-leak protection
-------------------------------
The :class:`TokenRedactionFilter` installed by ``configure_logging``
redacts any substring that matches an access-token, refresh-token,
or API-key pattern. This is a defence-in-depth measure.

Usage:
    from infrastructure.logging_config import configure_logging, get_logger

    # Configure at application startup
    configure_logging(service="api", level="INFO")

    # Get a structured logger
    logger = get_logger(__name__)
    logger.info("Order placed", extra={"order_id": "123", "symbol": "RELIANCE"})
"""

from __future__ import annotations

import json
import logging
import logging.config
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any

# Token redaction patterns
_TOKEN_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(access_token\s*=\s*)([^\s,;]+)", re.IGNORECASE),
    re.compile(r"(refresh_token\s*=\s*)([^\s,;]+)", re.IGNORECASE),
    re.compile(r"(api_key\s*=\s*)([^\s,;]+)", re.IGNORECASE),
    re.compile(r"(api_secret\s*=\s*)([^\s,;]+)", re.IGNORECASE),
    re.compile(r"(password\s*=\s*)([^\s,;]+)", re.IGNORECASE),
    re.compile(r"(authorization:\s*Bearer\s+)([^\s,;]+)", re.IGNORECASE),
    re.compile(r"([?&]token=)([^&\s\"']+)", re.IGNORECASE),
    re.compile(r"((?:DHAN|UPSTOX|ZERODHA|ANGEL)[A-Z_]*TOKEN\s*=\s*)([^\s,;]+)"),
    re.compile(r"\b([A-Za-z0-9_\-]{32,})\b"),
)

_SENSITIVE_EXTRA_KEYS: frozenset[str] = frozenset({
    "token", "access_token", "refresh_token", "api_key", "api_secret",
    "password", "pin", "totp", "totp_secret", "authorization", "bearer_token",
})


class TokenRedactionFilter(logging.Filter):
    """Redact token-like substrings from log records."""

    REDACTED = "<REDACTED>"

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        redacted = _redact(msg)
        if redacted != msg:
            record.msg = redacted
            record.args = ()
        _redact_record_extras(record)
        return True


def _redact_record_extras(record: logging.LogRecord) -> None:
    """Redact sensitive values in structured extra fields."""
    for key, value in list(record.__dict__.items()):
        if key in _LOG_RECORD_BUILTIN_KEYS:
            continue
        key_lower = key.lower()
        if key_lower in _SENSITIVE_EXTRA_KEYS or key_lower.endswith("_token"):
            if isinstance(value, str) and value:
                record.__dict__[key] = TokenRedactionFilter.REDACTED
            continue
        if isinstance(value, str) and value:
            record.__dict__[key] = _redact(value)


_LOG_RECORD_BUILTIN_KEYS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__)


def _redact(text: str) -> str:
    """Apply every token redaction pattern to text."""
    for pattern in _TOKEN_PATTERNS:
        text = pattern.sub(_replace, text)
    return text


def _replace(match: re.Match[str]) -> str:
    """Substitute captured group with REDACTED."""
    groups = match.groups()
    if len(groups) >= 2 and groups[-1] and groups[0]:
        return f"{groups[0]}{TokenRedactionFilter.REDACTED}"
    return TokenRedactionFilter.REDACTED


class CorrelationFilter(logging.Filter):
    """Inject correlation_id and service_name into every log record."""

    def __init__(self, service_name: str | None = None) -> None:
        super().__init__()
        import os
        self.service_name = service_name or os.getenv("TRADING_SERVICE_NAME", "trading-platform")

    def filter(self, record: logging.LogRecord) -> bool:
        from infrastructure.correlation import get_current_correlation_id

        record.correlation_id = get_current_correlation_id() or "no-correlation"
        record.service_name = self.service_name
        return True


class StructuredFormatter(logging.Formatter):
    """JSON-structured log formatter for production use."""

    def __init__(self, service: str = "tradexv2") -> None:
        super().__init__()
        self._service = service

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "service": self._service,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "thread": record.threadName,
            "process": record.process,
        }
        correlation_id = getattr(record, "correlation_id", "")
        if correlation_id:
            log_entry["correlation_id"] = correlation_id
        service_name = getattr(record, "service_name", "")
        if service_name:
            log_entry["service_name"] = service_name
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": self.formatException(record.exc_info),
            }
        for key, value in record.__dict__.items():
            if key not in _LOG_RECORD_BUILTIN_KEYS:
                log_entry[key] = value
        return json.dumps(log_entry, default=str)


class HumanReadableFormatter(logging.Formatter):
    """Human-readable log formatter for development use."""

    COLORS = {
        "DEBUG": "\033[36m", "INFO": "\033[32m", "WARNING": "\033[33m",
        "ERROR": "\033[31m", "CRITICAL": "\033[41m",
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created, tz=timezone.utc).strftime("%H:%M:%S.%f")[:-3]
        color = self.COLORS.get(record.levelname, "")
        level = f"{record.levelname:<8}"
        correlation_id = getattr(record, "correlation_id", "")
        corr_str = f" [{correlation_id}]" if correlation_id else ""
        message = record.getMessage()
        if record.exc_info and record.exc_info[0]:
            message += f" | {record.exc_info[0].__name__}: {record.exc_info[1]}"
        extra_parts = []
        for key, value in record.__dict__.items():
            if key not in _LOG_RECORD_BUILTIN_KEYS and key not in ("correlation_id", "service_name"):
                extra_parts.append(f"{key}={value}")
        extra_str = " ".join(extra_parts)
        if extra_str:
            message += f" - {extra_str}"
        return f"{color}{timestamp}{self.RESET} {color}{level}{self.RESET} {record.name:<30} {message}{corr_str}"


def configure_logging(
    service: str = "tradexv2",
    level: str | None = None,
    log_format: str | None = None,
    log_file: str | None = None,
    enable_redaction: bool = True,
) -> None:
    """Configure logging for the entire application.

    Args:
        service: Service name for log identification.
        level: Log level (DEBUG, INFO, WARNING, ERROR). Defaults to env var
            XV2_LOG_LEVEL or INFO.
        log_format: 'json' for structured, 'human' for readable. Defaults to
            'json' in production, 'human' otherwise.
        log_file: Optional file path for log output.
        enable_redaction: If True (default), install TokenRedactionFilter.
    """
    if level is None:
        level = os.environ.get("XV2_LOG_LEVEL", "INFO")
    level = level.upper()

    if log_format is None:
        is_production = os.environ.get("APP_ENV", "").lower() in ("prod", "production")
        log_format = "json" if is_production else "human"

    if log_format == "json":
        formatter = StructuredFormatter(service=service)
    else:
        formatter = HumanReadableFormatter()

    handler_filters = ["correlation"]
    if enable_redaction:
        handler_filters.insert(0, "token_redaction")

    handlers: dict[str, Any] = {
        "console": {
            "class": "logging.StreamHandler",
            "stream": sys.stdout,
            "formatter": "standard",
            "filters": handler_filters,
        }
    }

    if log_file:
        handlers["file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": log_file,
            "maxBytes": 10 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "standard",
            "filters": handler_filters,
        }

    filters: dict[str, Any] = {}
    if enable_redaction:
        filters["token_redaction"] = {"()": "infrastructure.logging_config.TokenRedactionFilter"}
    filters["correlation"] = {"()": "infrastructure.logging_config.CorrelationFilter"}

    config: dict[str, Any] = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"standard": {"()": lambda: formatter}},
        "filters": filters,
        "handlers": handlers,
        "root": {"level": level, "handlers": list(handlers.keys())},
        "loggers": {
            "urllib3": {"level": "WARNING", "handlers": list(handlers.keys())},
            "httpx": {"level": "WARNING", "handlers": list(handlers.keys())},
            "websockets": {"level": "WARNING", "handlers": list(handlers.keys())},
            "asyncio": {"level": "WARNING", "handlers": list(handlers.keys())},
        },
    }

    logging.config.dictConfig(config)

    logger = logging.getLogger(__name__)
    logger.info(
        "Logging configured",
        extra={"service": service, "level": level, "format": log_format, "log_file": log_file},
    )


def get_logger(name: str) -> logging.Logger:
    """Get a structured logger instance."""
    return logging.getLogger(name)


def set_production_mode(enabled: bool) -> None:
    """Override production mode detection (for testing)."""
    os.environ["APP_ENV"] = "production" if enabled else "development"


# Backward-compat aliases for the old module name
ConsoleFormatter = HumanReadableFormatter
JSONFormatter = StructuredFormatter


__all__ = [
    "ConsoleFormatter",
    "CorrelationFilter",
    "HumanReadableFormatter",
    "JSONFormatter",
    "StructuredFormatter",
    "TokenRedactionFilter",
    "configure_logging",
    "get_logger",
    "set_production_mode",
]
