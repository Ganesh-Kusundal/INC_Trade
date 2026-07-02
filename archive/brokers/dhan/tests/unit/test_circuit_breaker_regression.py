"""DH-906 circuit breaker regression tests (Dhan-specific).

Moved from brokers/common/oms/tests/test_oms_e2e.py as part of
REF-012 import-linter enforcement. These tests exercise Dhan-specific
HTTP client and circuit breaker behavior.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from brokers.common.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
)


def test_dhan_place_order_with_read_cb_open_still_posts_order() -> None:
    """A read CB that is OPEN must NOT block a POST /orders call.

    The original DH-906 incident was caused by a single
    CircuitBreaker("dhan-api") being used for every endpoint; a
    storm of failed option-chain reads opened the breaker and the
    order placement was blocked. Phase A / A1 split the breaker into
    read / write / admin categories. This test pins that split.
    """
    from brokers.dhan.exceptions import DhanError
    from brokers.dhan.http_client import DhanHttpClient

    cb_read = CircuitBreaker(
        "test-read", CircuitBreakerConfig(failure_threshold=1, open_duration_ms=30_000)
    )
    cb_write = CircuitBreaker(
        "test-write", CircuitBreakerConfig(failure_threshold=10, open_duration_ms=30_000)
    )
    client = DhanHttpClient(
        client_id="X",
        access_token="T",
        read_circuit_breaker=cb_read,
        write_circuit_breaker=cb_write,
    )
    # Bypass throttle to keep the test fast.
    client._throttle = lambda *a, **kw: None  # type: ignore[assignment]

    # Drive the read CB past its threshold with one failed read.
    resp_503 = MagicMock()
    resp_503.status_code = 503
    resp_503.text = "boom"
    client._session.request = MagicMock(return_value=resp_503)
    with pytest.raises(DhanError):
        client.get("/marketfeed/quote")
    assert cb_read.state == CircuitState.OPEN

    # Now attempt a POST /orders. The read CB is OPEN, the write CB
    # is CLOSED — the request must NOT be blocked.
    resp_200 = MagicMock()
    resp_200.status_code = 200
    resp_200.text = "{}"
    resp_200.json.return_value = {"orderId": "ORD-1", "status": "success"}
    client._session.request = MagicMock(return_value=resp_200)

    result = client.post("/orders", json={"symbol": "RELIANCE"})
    assert result == {"orderId": "ORD-1", "status": "success"}
    assert cb_write.state == CircuitState.CLOSED


def test_dhan_post_orders_with_write_cb_open_fails_fast() -> None:
    """The inverse: a write CB that is OPEN must fast-fail a POST /orders call."""
    from brokers.dhan.exceptions import DhanError
    from brokers.dhan.http_client import DhanHttpClient

    cb_write = CircuitBreaker(
        "test-write", CircuitBreakerConfig(failure_threshold=1, open_duration_ms=30_000)
    )
    client = DhanHttpClient(
        client_id="X",
        access_token="T",
        write_circuit_breaker=cb_write,
    )
    client._throttle = lambda *a, **kw: None  # type: ignore[assignment]

    # Trip the write CB with one failed POST.
    resp_503 = MagicMock()
    resp_503.status_code = 503
    resp_503.text = "boom"
    client._session.request = MagicMock(return_value=resp_503)
    with pytest.raises(DhanError):
        client.post("/orders", json={"symbol": "X"})
    assert cb_write.state == CircuitState.OPEN

    # A second POST must fast-fail.
    client._session.request = MagicMock(
        side_effect=AssertionError("session.request should NOT be called when CB is OPEN")
    )
    with pytest.raises(DhanError, match="Circuit breaker open"):
        client.post("/orders", json={"symbol": "X"})
