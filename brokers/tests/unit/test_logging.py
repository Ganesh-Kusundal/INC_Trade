"""Tests for structured logging and token redaction."""

from __future__ import annotations

import json
import logging

from brokers.infrastructure.logging import (
    CorrelationFilter,
    StructuredFormatter,
    TokenRedactionFilter,
)


class TestTokenRedactionFilter:
    def setup_method(self):
        self.filter = TokenRedactionFilter()

    def _make_record(self, msg: str) -> logging.LogRecord:
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg=msg,
            args=(),
            exc_info=None,
        )
        return record

    def test_redacts_access_token(self):
        record = self._make_record("access_token=abc123secret")
        self.filter.filter(record)
        assert "abc123secret" not in record.msg
        assert "[REDACTED]" in record.msg

    def test_redacts_api_key(self):
        record = self._make_record("api_key: my-secret-key-value")
        self.filter.filter(record)
        assert "my-secret-key-value" not in record.msg

    def test_redacts_bearer_token(self):
        record = self._make_record("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9")
        self.filter.filter(record)
        assert "eyJhbGciOiJIUzI1NiJ9" not in record.msg

    def test_redacts_long_tokens(self):
        long_token = "a" * 40
        record = self._make_record(f"token={long_token}")
        self.filter.filter(record)
        assert long_token not in record.msg

    def test_passes_normal_messages(self):
        record = self._make_record("order placed successfully")
        self.filter.filter(record)
        assert record.msg == "order placed successfully"


class TestCorrelationFilter:
    def test_injects_correlation_id(self):
        from brokers.infrastructure.correlation import with_correlation

        cf = CorrelationFilter()
        with with_correlation("test-corr-123"):
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="",
                lineno=0,
                msg="hello",
                args=(),
                exc_info=None,
            )
            cf.filter(record)
            assert record.correlation_id == "test-corr-123"

    def test_empty_when_no_context(self):
        cf = CorrelationFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="hello",
            args=(),
            exc_info=None,
        )
        cf.filter(record)
        assert record.correlation_id == ""


class TestStructuredFormatter:
    def test_produces_valid_json(self):
        fmt = StructuredFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test message",
            args=(),
            exc_info=None,
        )
        record.correlation_id = "corr-abc"
        output = fmt.format(record)
        parsed = json.loads(output)
        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "test.logger"
        assert parsed["message"] == "test message"
        assert parsed["correlation_id"] == "corr-abc"

    def test_includes_extra_fields(self):
        fmt = StructuredFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="order",
            args=(),
            exc_info=None,
        )
        record.correlation_id = ""
        record.order_id = "ORD-001"
        record.symbol = "RELIANCE"
        output = fmt.format(record)
        parsed = json.loads(output)
        assert parsed["extra"]["order_id"] == "ORD-001"
        assert parsed["extra"]["symbol"] == "RELIANCE"
