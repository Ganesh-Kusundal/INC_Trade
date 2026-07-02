"""Tests for A1: DhanHttpClient category-specific circuit breakers.

The previous implementation used a single ``CircuitBreaker("dhan-api")`` for
every endpoint. A storm of failed reads (e.g. option-chain during a
volatile session) would OPEN the breaker and block order placement.

These tests verify the split:
  - read endpoint failure does NOT open the write CB
  - write endpoint failure does NOT open the read CB
  - admin endpoint failure does NOT open the read or write CB
  - the backwards-compat single-CB path still works
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from brokers.common.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
)
from brokers.dhan.exceptions import DhanError
from brokers.dhan.http_client import (
    DhanHttpClient,
    _categorize_endpoint,
)

# ── Endpoint categorization ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "endpoint,expected_category",
    [
        # Read endpoints
        ("/marketfeed/ltp", "read"),
        ("/marketfeed/quote", "read"),
        ("/marketfeed/ohlc", "read"),
        ("/charts/historical", "read"),
        ("/charts/intraday", "read"),
        ("/optionchain", "read"),
        ("/optionchain/expirylist", "read"),
        ("/marketstatus", "read"),
        ("/instruments", "read"),
        # Write endpoints
        ("/orders", "write"),
        ("/killswitch", "write"),
        ("/sliceorder", "write"),
        # Admin (default for everything else)
        ("/fundlimit", "admin"),
        ("/positions", "admin"),
        ("/holdings", "admin"),
        ("/trades", "admin"),
        ("/traderbook", "admin"),
        ("/access/token", "admin"),
        ("/some/random/endpoint", "admin"),
    ],
)
def test_categorize_endpoint(endpoint: str, expected_category: str) -> None:
    assert _categorize_endpoint(endpoint) == expected_category


# ── Test helpers ─────────────────────────────────────────────────────────


def _make_client(
    cb_read: CircuitBreaker | None = None,
    cb_write: CircuitBreaker | None = None,
    cb_admin: CircuitBreaker | None = None,
    cb_legacy: CircuitBreaker | None = None,
) -> DhanHttpClient:
    """Build a DhanHttpClient with the requested CBs and a stubbed
    session that lets us return canned responses."""
    return DhanHttpClient(
        client_id="test",
        access_token="token",
        read_circuit_breaker=cb_read,
        write_circuit_breaker=cb_write,
        admin_circuit_breaker=cb_admin,
        circuit_breaker=cb_legacy,
    )


def _stub_response(
    client: DhanHttpClient, endpoint: str, *, status: int, body: dict | None = None
) -> None:
    """Patch ``client._session.request`` to return a single canned
    response. For a 5xx we want the failure recorded; for a 200 we
    want a successful response."""
    resp = MagicMock()
    resp.status_code = status
    resp.text = json.dumps(body) if body is not None else ""
    resp.json.return_value = body if body is not None else {}
    client._session.request = MagicMock(return_value=resp)


# ── Read endpoint failure does not affect write CB ──────────────────────


def test_read_endpoint_failures_do_not_open_write_circuit_breaker() -> None:
    """5xx on a read endpoint must be recorded on the read CB only.
    The write CB must remain CLOSED so order placement is unaffected."""
    cb_read = CircuitBreaker(
        "test-read", CircuitBreakerConfig(failure_threshold=2, open_duration_ms=30_000)
    )
    cb_write = CircuitBreaker(
        "test-write", CircuitBreakerConfig(failure_threshold=2, open_duration_ms=30_000)
    )
    cb_admin = CircuitBreaker(
        "test-admin", CircuitBreakerConfig(failure_threshold=2, open_duration_ms=30_000)
    )
    client = _make_client(cb_read=cb_read, cb_write=cb_write, cb_admin=cb_admin)

    # Drive the read CB past its threshold with 2 failed reads.
    for _ in range(2):
        _stub_response(client, "/marketfeed/quote", status=503)
        with pytest.raises(DhanError):
            client.get("/marketfeed/quote")

    assert cb_read.state == CircuitState.OPEN, "Read CB should be OPEN after 2 failures"
    assert cb_write.state == CircuitState.CLOSED, "Write CB must remain CLOSED"
    assert cb_admin.state == CircuitState.CLOSED, "Admin CB must remain CLOSED"


def test_write_endpoint_failures_do_not_open_read_circuit_breaker() -> None:
    """A failed place_order must NOT take out the read or admin CBs."""
    cb_read = CircuitBreaker(
        "test-read", CircuitBreakerConfig(failure_threshold=10, open_duration_ms=30_000)
    )
    cb_write = CircuitBreaker(
        "test-write", CircuitBreakerConfig(failure_threshold=2, open_duration_ms=30_000)
    )
    cb_admin = CircuitBreaker(
        "test-admin", CircuitBreakerConfig(failure_threshold=10, open_duration_ms=30_000)
    )
    client = _make_client(cb_read=cb_read, cb_write=cb_write, cb_admin=cb_admin)

    for _ in range(2):
        _stub_response(client, "/orders", status=503)
        with pytest.raises(DhanError):
            client.post("/orders", json={"symbol": "RELIANCE"})

    assert cb_write.state == CircuitState.OPEN
    assert cb_read.state == CircuitState.CLOSED
    assert cb_admin.state == CircuitState.CLOSED


def test_admin_endpoint_failures_do_not_open_read_or_write_circuit_breaker() -> None:
    """A failed /positions call must NOT take out the read or write CBs."""
    cb_read = CircuitBreaker(
        "test-read", CircuitBreakerConfig(failure_threshold=10, open_duration_ms=30_000)
    )
    cb_write = CircuitBreaker(
        "test-write", CircuitBreakerConfig(failure_threshold=10, open_duration_ms=30_000)
    )
    cb_admin = CircuitBreaker(
        "test-admin", CircuitBreakerConfig(failure_threshold=2, open_duration_ms=30_000)
    )
    client = _make_client(cb_read=cb_read, cb_write=cb_write, cb_admin=cb_admin)

    for _ in range(2):
        _stub_response(client, "/positions", status=503)
        with pytest.raises(DhanError):
            client.get("/positions")

    assert cb_admin.state == CircuitState.OPEN
    assert cb_read.state == CircuitState.CLOSED
    assert cb_write.state == CircuitState.CLOSED


# ── Open CB short-circuits requests in its category only ─────────────────


def test_open_read_circuit_breaker_does_not_block_writes() -> None:
    """When the read CB is OPEN, read requests fast-fail but a write
    request must still go through to the wire. This is the
    pre-A1 failure mode we are fixing."""
    cb_read = CircuitBreaker(
        "test-read", CircuitBreakerConfig(failure_threshold=1, open_duration_ms=30_000)
    )
    cb_write = CircuitBreaker(
        "test-write", CircuitBreakerConfig(failure_threshold=10, open_duration_ms=30_000)
    )
    cb_admin = CircuitBreaker(
        "test-admin", CircuitBreakerConfig(failure_threshold=10, open_duration_ms=30_000)
    )
    client = _make_client(cb_read=cb_read, cb_write=cb_write, cb_admin=cb_admin)

    # Trip the read CB.
    _stub_response(client, "/marketfeed/quote", status=503)
    with pytest.raises(DhanError):
        client.get("/marketfeed/quote")
    assert cb_read.state == CircuitState.OPEN

    # A write request must not be blocked.
    _stub_response(client, "/orders", status=200, body={"orderId": "ORD-1", "status": "success"})
    result = client.post("/orders", json={"symbol": "RELIANCE"})
    assert result == {"orderId": "ORD-1", "status": "success"}


def test_open_write_circuit_breaker_does_not_block_reads() -> None:
    """Symmetric: an OPEN write CB must not block reads."""
    cb_read = CircuitBreaker(
        "test-read", CircuitBreakerConfig(failure_threshold=10, open_duration_ms=30_000)
    )
    cb_write = CircuitBreaker(
        "test-write", CircuitBreakerConfig(failure_threshold=1, open_duration_ms=30_000)
    )
    cb_admin = CircuitBreaker(
        "test-admin", CircuitBreakerConfig(failure_threshold=10, open_duration_ms=30_000)
    )
    client = _make_client(cb_read=cb_read, cb_write=cb_write, cb_admin=cb_admin)

    _stub_response(client, "/orders", status=503)
    with pytest.raises(DhanError):
        client.post("/orders", json={"symbol": "X"})
    assert cb_write.state == CircuitState.OPEN

    _stub_response(client, "/marketfeed/quote", status=200, body={"data": {"ltp": 100}})
    result = client.get("/marketfeed/quote")
    assert result == {"data": {"ltp": 100}}


# ── Backwards-compat: single CB argument routes to all categories ───────


def test_legacy_single_circuit_breaker_routes_to_all_categories() -> None:
    """If only the legacy ``circuit_breaker`` argument is passed, every
    category uses that single CB. This preserves every existing
    test fixture and external caller.
    """
    legacy = CircuitBreaker(
        "legacy", CircuitBreakerConfig(failure_threshold=2, open_duration_ms=30_000)
    )
    client = _make_client(cb_legacy=legacy)

    # A read failure increments the same CB.
    _stub_response(client, "/marketfeed/quote", status=503)
    with pytest.raises(DhanError):
        client.get("/marketfeed/quote")

    # A write failure increments the SAME CB.
    _stub_response(client, "/orders", status=503)
    with pytest.raises(DhanError):
        client.post("/orders", json={"symbol": "X"})

    # Now an admin failure trips the breaker (3rd failure total).
    _stub_response(client, "/positions", status=503)
    with pytest.raises(DhanError):
        client.get("/positions")

    # The legacy CB is now OPEN — confirming all categories routed
    # through it. (This is the pre-A1 behaviour.)
    assert legacy.state == CircuitState.OPEN


def test_specific_cbs_override_legacy_when_both_provided() -> None:
    """If both ``circuit_breaker`` and a category-specific CB are
    passed, the category-specific one wins. The legacy is used only
    for any category that does NOT have its own CB.
    """
    legacy = CircuitBreaker(
        "legacy", CircuitBreakerConfig(failure_threshold=2, open_duration_ms=30_000)
    )
    cb_write = CircuitBreaker(
        "write", CircuitBreakerConfig(failure_threshold=2, open_duration_ms=30_000)
    )
    client = _make_client(cb_write=cb_write, cb_legacy=legacy)

    # 2 write failures open ONLY the write CB.
    for _ in range(2):
        _stub_response(client, "/orders", status=503)
        with pytest.raises(DhanError):
            client.post("/orders", json={"symbol": "X"})

    assert cb_write.state == CircuitState.OPEN
    # Legacy was not touched by the write path.
    assert legacy.state == CircuitState.CLOSED

    # A read still uses the legacy (since no read CB was provided).
    _stub_response(client, "/marketfeed/quote", status=503)
    with pytest.raises(DhanError):
        client.get("/marketfeed/quote")
    # legacy now at 1 failure (still CLOSED, threshold=2)


# ── Internal helper: _get_circuit_breaker ───────────────────────────────


def test_get_circuit_breaker_routes_by_category() -> None:
    cb_read = CircuitBreaker("r", CircuitBreakerConfig())
    cb_write = CircuitBreaker("w", CircuitBreakerConfig())
    cb_admin = CircuitBreaker("a", CircuitBreakerConfig())
    client = _make_client(cb_read=cb_read, cb_write=cb_write, cb_admin=cb_admin)

    assert client._get_circuit_breaker("/marketfeed/quote") is cb_read
    assert client._get_circuit_breaker("/optionchain") is cb_read
    assert client._get_circuit_breaker("/orders") is cb_write
    assert client._get_circuit_breaker("/killswitch") is cb_write
    assert client._get_circuit_breaker("/positions") is cb_admin
    assert client._get_circuit_breaker("/fundlimit") is cb_admin
    assert client._get_circuit_breaker("/anything/else") is cb_admin


def test_get_circuit_breaker_falls_back_to_legacy() -> None:
    legacy = CircuitBreaker("legacy", CircuitBreakerConfig())
    client = _make_client(cb_legacy=legacy)
    assert client._get_circuit_breaker("/marketfeed/quote") is legacy
    assert client._get_circuit_breaker("/orders") is legacy
    assert client._get_circuit_breaker("/positions") is legacy
