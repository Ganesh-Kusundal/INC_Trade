"""Structured logging with token redaction and correlation ID injection.

Provides:
- StructuredFormatter: JSON log format for machine-parseable output
- TokenRedactionFilter: strips secrets from log messages
- CorrelationFilter: injects correlation_id from contextvars
- configure_logging(): one-call setup
"""

from __future__ import annotations

import json
import logging
import re
import sys
from typing import Any

_REDACTION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r'(bearer\s+)[^\s,}"\']+', re.I), r"\1[REDACTED]"),
    (re.compile(r'(access_token["\s:=]+)[^\s,}"\']+', re.I), r"\1[REDACTED]"),
    (re.compile(r'(refresh_token["\s:=]+)[^\s,}"\']+', re.I), r"\1[REDACTED]"),
    (re.compile(r'(api_key["\s:=]+)[^\s,}"\']+', re.I), r"\1[REDACTED]"),
    (re.compile(r'(api_secret["\s:=]+)[^\s,}"\']+', re.I), r"\1[REDACTED]"),
    (re.compile(r'(password["\s:=]+)[^\s,}"\']+', re.I), r"\1[REDACTED]"),
    (re.compile(r'(client_secret["\s:=]+)[^\s,}"\']+', re.I), r"\1[REDACTED]"),
    (re.compile(r'(authorization["\s:=]+)[^\s,}"\']+', re.I), r"\1[REDACTED]"),
    (re.compile(r"\b([a-zA-Z0-9]{32,})\b"), r"[REDACTED_TOKEN]"),
]


class TokenRedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self._redact(record.msg)
        return True

    @staticmethod
    def _redact(text: str) -> str:
        for pattern, replacement in _REDACTION_PATTERNS:
            text = pattern.sub(replacement, text)
        return text


class CorrelationFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        from brokers.infrastructure.correlation import get_current_correlation_id

        record.correlation_id = get_current_correlation_id()
        return True


class StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        extra_fields: dict[str, Any] = {}
        for key in (
            "order_id",
            "symbol",
            "exchange",
            "side",
            "quantity",
            "message",
            "error_code",
            "latency_ms",
        ):
            val = getattr(record, key, None)
            if val is not None:
                extra_fields[key] = val

        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": getattr(record, "correlation_id", ""),
        }
        if extra_fields:
            payload["extra"] = extra_fields
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(
    service_name: str = "tradexv2",
    level: int = logging.INFO,
) -> None:
    root = logging.getLogger()
    root.setLevel(level)

    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(level)
    handler.setFormatter(StructuredFormatter())
    handler.addFilter(TokenRedactionFilter())
    handler.addFilter(CorrelationFilter())

    root.handlers.clear()
    root.addHandler(handler)

    logging.getLogger().name = service_name
