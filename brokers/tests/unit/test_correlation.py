"""Tests for correlation ID management."""

from __future__ import annotations

from inc_trade.infrastructure.correlation import (
    generate_correlation_id,
    get_current_correlation_id,
    set_current_correlation_id,
    with_correlation,
)


class TestCorrelationId:
    def test_generate_returns_string(self):
        cid = generate_correlation_id()
        assert isinstance(cid, str)
        assert len(cid) == 32

    def test_generate_unique(self):
        ids = {generate_correlation_id() for _ in range(100)}
        assert len(ids) == 100

    def test_default_is_empty(self):
        assert get_current_correlation_id() == ""

    def test_set_and_get(self):
        token = set_current_correlation_id("test-123")
        try:
            assert get_current_correlation_id() == "test-123"
        finally:
            from inc_trade.infrastructure.correlation import _correlation_id_var

            _correlation_id_var.reset(token)


class TestWithCorrelation:
    def test_sets_and_restores(self):
        assert get_current_correlation_id() == ""
        with with_correlation("ctx-abc"):
            assert get_current_correlation_id() == "ctx-abc"
        assert get_current_correlation_id() == ""

    def test_auto_generates_if_none(self):
        with with_correlation() as cid:
            assert len(cid) == 32
            assert get_current_correlation_id() == cid

    def test_nested_contexts(self):
        with with_correlation("outer"):
            assert get_current_correlation_id() == "outer"
            with with_correlation("inner"):
                assert get_current_correlation_id() == "inner"
            assert get_current_correlation_id() == "outer"
        assert get_current_correlation_id() == ""
