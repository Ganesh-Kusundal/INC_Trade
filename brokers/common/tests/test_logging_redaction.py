"""Tests for the token-leak redaction filter (REF-29).

These tests run against the filter in isolation — no dictConfig — so
they are fast and do not pollute the global logger state.
"""

from __future__ import annotations

import io
import logging

import pytest

from infrastructure.logging_config import TokenRedactionFilter, _redact

# ---------- pure-Python tests (no logger side effects) ----------


class TestRedact:
    def test_redacts_access_token_keyword(self):
        assert _redact("got access_token=abcd1234efgh5678") == "got access_token=<REDACTED>"

    def test_redacts_refresh_token_keyword(self):
        assert _redact("refresh_token=xyz") == "refresh_token=<REDACTED>"

    def test_redacts_bearer_authorization(self):
        out = _redact("authorization: Bearer abc.def.ghi")
        assert "abc.def.ghi" not in out
        assert "<REDACTED>" in out

    def test_redacts_dhan_env_var_token(self):
        out = _redact("export DHAN_ACCESS_TOKEN=verysecretvalue1234")
        assert "verysecretvalue1234" not in out
        assert "<REDACTED>" in out

    def test_redacts_upstox_env_var_token(self):
        out = _redact("UPSTOX_ACCESS_TOKEN=abc12345def67890ghi")
        assert "abc12345def67890ghi" not in out
        assert "<REDACTED>" in out

    def test_redacts_api_key(self):
        assert _redact("api_key=sk_live_abcdef1234567890") == "api_key=<REDACTED>"

    def test_redacts_password(self):
        assert _redact("password=hunter2") == "password=<REDACTED>"

    def test_redacts_long_base64url_token(self):
        long_token = "A" * 40
        out = _redact(f"raw token: {long_token}")
        assert long_token not in out
        assert "<REDACTED>" in out

    def test_does_not_redact_short_strings(self):
        # 32-char threshold is intentional. Strings shorter than
        # that are common (UUIDs, hashes) and redacting them would
        # make logs unreadable.
        out = _redact("request id: 12345678")
        assert out == "request id: 12345678"

    def test_idempotent(self):
        # Running redact twice on an already-redacted string should
        # be a no-op so the filter is safe to call from multiple
        # handlers.
        once = _redact("access_token=abcd1234efgh5678")
        twice = _redact(once)
        assert once == twice

    def test_empty_string_passes_through(self):
        assert _redact("") == ""

    def test_multiple_tokens_in_one_message(self):
        msg = "first access_token=aaaaaa second refresh_token=bbbbbb"
        out = _redact(msg)
        assert "aaaaaa" not in out
        assert "bbbbbb" not in out
        assert out.count("<REDACTED>") == 2

    def test_preserves_prefix(self):
        # The prefix (``access_token=``) must remain so operators
        # can see WHICH credential was supposed to be in that
        # position — only the value is redacted.
        out = _redact("DEBUG access_token=secret123")
        assert out.startswith("DEBUG access_token=<REDACTED>")


# ---------- filter-integration tests (use real LogRecord) ----------


@pytest.fixture
def logger_with_filter() -> logging.Logger:
    """Build a private logger wired to a StringIO handler with the filter."""
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.addFilter(TokenRedactionFilter())
    handler.setLevel(logging.DEBUG)

    log = logging.getLogger("test_redaction")
    log.handlers = [handler]
    log.setLevel(logging.DEBUG)
    log.propagate = False
    return log


class TestFilterIntegration:
    def test_filter_redacts_formatted_message(self, logger_with_filter):
        # Use a realistic keyword-prefixed token. The bare ``token=``
        # keyword is intentionally NOT in the redaction pattern list
        # to avoid redacting identifiers like ``request_token=...``.
        logger_with_filter.info("access_token=%s", "supersecretvalue1234567890")
        output = logger_with_filter.handlers[0].stream.getvalue()
        assert "supersecretvalue1234567890" not in output
        assert "<REDACTED>" in output

    def test_filter_redacts_fstring_style_message(self, logger_with_filter):
        token = "A" * 40
        logger_with_filter.info("got token %s", token)
        output = logger_with_filter.handlers[0].stream.getvalue()
        assert token not in output
        assert "<REDACTED>" in output

    def test_filter_passes_through_normal_message(self, logger_with_filter):
        logger_with_filter.info("hello world")
        output = logger_with_filter.handlers[0].stream.getvalue()
        assert "hello world" in output

    def test_filter_returns_true(self):
        # ``filter`` must always return True so the message is
        # emitted (redacted) — never drop records entirely.
        record = logging.LogRecord(
            name="x",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="access_token=secret",
            args=(),
            exc_info=None,
        )
        assert TokenRedactionFilter().filter(record) is True

    def test_filter_handles_record_with_args_safely(self, logger_with_filter):
        logger_with_filter.info("token=%s", "abcdefghij" * 4)
        output = logger_with_filter.handlers[0].stream.getvalue()
        assert "abcdefghijabcdefghijabcdefghijabcdefghij" not in output

    def test_filter_redacts_sensitive_extra_fields(self):
        record = logging.LogRecord(
            name="x",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="token_refresh",
            args=(),
            exc_info=None,
        )
        record.access_token = "supersecretvalue1234567890"
        record.client_id = "1106"
        TokenRedactionFilter().filter(record)
        assert record.access_token == "<REDACTED>"
        assert record.client_id == "1106"
