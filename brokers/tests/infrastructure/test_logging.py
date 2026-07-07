"""Tests for structured logging adapter."""

from __future__ import annotations

import logging

from brokers.infrastructure.logging import (
    StructuredLogger,
    _StructuredFormatter,
    get_logger,
)


class TestStructuredFormatter:
    def test_formats_event_with_kwargs(self):
        fmt = _StructuredFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="order_placed", args=(), exc_info=None,
        )
        record.structured = {"order_id": "ord_123", "symbol": "RELIANCE"}
        record.created = 1719900000.0

        output = fmt.format(record)
        assert "order_placed" in output
        assert "order_id=ord_123" in output
        assert "symbol=RELIANCE" in output

    def test_quotes_values_with_spaces(self):
        fmt = _StructuredFormatter()
        record = logging.LogRecord(
            name="test", level=logging.WARNING, pathname="", lineno=0,
            msg="error_event", args=(), exc_info=None,
        )
        record.structured = {"message": "bad quantity"}
        record.created = 1719900000.0

        output = fmt.format(record)
        assert 'message="bad quantity"' in output

    def test_handles_none_value(self):
        fmt = _StructuredFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="event", args=(), exc_info=None,
        )
        record.structured = {"correlation_id": None}
        record.created = 1719900000.0

        output = fmt.format(record)
        assert "correlation_id=null" in output


class TestStructuredLogger:
    def test_logger_creation(self):
        logger = get_logger("test_logger")
        assert isinstance(logger, StructuredLogger)

    def test_same_name_returns_same_instance(self):
        a = get_logger("test_reuse")
        b = get_logger("test_reuse")
        assert a is b

    def test_different_names_return_different_instances(self):
        a = get_logger("test_a")
        b = get_logger("test_b")
        assert a is not b

    def test_logger_has_all_levels(self):
        logger = get_logger("test_levels")
        assert hasattr(logger, "debug")
        assert hasattr(logger, "info")
        assert hasattr(logger, "warning")
        assert hasattr(logger, "error")
        assert hasattr(logger, "critical")
        assert hasattr(logger, "exception")

    def test_with_context_returns_child(self):
        logger = get_logger("test_ctx")
        child = logger.with_context(broker_id="dhan", env="sandbox")
        assert isinstance(child, StructuredLogger)
        assert child is not logger
