"""REF-13: token-broadcast / receiver-list contract tests.

The previous design only refreshed the HTTP client and the market
feed on token rotation. Order stream and depth feeds kept the stale
token until their next reconnect, which was the documented DH-906
incident failure mode. This module verifies the new
``register_token_receiver`` / ``broadcast_token`` contract:

* any callable accepting a single string is accepted as a receiver,
* registration is idempotent,
* broadcast isolates per-receiver failures,
* a registered receiver is called for every broadcast.

These tests do not use a real Dhan connection; they drive the
public surface of :class:`DhanConnection` so they pass without
network access and remain stable across refactors.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from brokers.dhan.connection import DhanConnection


@pytest.fixture
def connection_with_mock_client() -> DhanConnection:
    """A bare DhanConnection whose HTTP client is a MagicMock."""
    client = MagicMock()
    client.client_id = "TEST"
    client.access_token = "initial-token"
    return DhanConnection(client=client)


def test_register_token_receiver_returns_receiver(connection_with_mock_client):
    conn = connection_with_mock_client

    def fn(t):
        return None

    assert conn.register_token_receiver(fn) is fn
    assert len(conn._token_manager._token_receivers) == 1
    assert conn._token_manager._token_receivers[0] == fn


def test_register_token_receiver_is_idempotent(connection_with_mock_client):
    conn = connection_with_mock_client

    def fn(t):
        return None

    conn.register_token_receiver(fn)
    conn.register_token_receiver(fn)
    assert len(conn._token_manager._token_receivers) == 1


def test_register_token_receiver_rejects_none(connection_with_mock_client):
    conn = connection_with_mock_client
    assert conn.register_token_receiver(None) is None  # type: ignore[arg-type]
    assert conn._token_manager._token_receivers == []


def test_broadcast_token_calls_all_receivers(connection_with_mock_client):
    conn = connection_with_mock_client
    a, b, c = MagicMock(), MagicMock(), MagicMock()
    conn.register_token_receiver(a)
    conn.register_token_receiver(b)
    conn.register_token_receiver(c)
    delivered = conn.broadcast_token("new-token")
    assert delivered == 3
    a.assert_called_once_with("new-token")
    b.assert_called_once_with("new-token")
    c.assert_called_once_with("new-token")


def test_broadcast_token_isolates_failing_receiver(connection_with_mock_client):
    conn = connection_with_mock_client
    a, b, c = MagicMock(), MagicMock(), MagicMock()
    b.side_effect = RuntimeError("boom")
    conn.register_token_receiver(a)
    conn.register_token_receiver(b)
    conn.register_token_receiver(c)
    delivered = conn.broadcast_token("new-token")
    assert delivered == 2
    a.assert_called_once_with("new-token")
    c.assert_called_once_with("new-token")


def test_broadcast_token_rejects_empty_string(connection_with_mock_client):
    conn = connection_with_mock_client
    a = MagicMock()
    conn.register_token_receiver(a)
    delivered = conn.broadcast_token("")
    assert delivered == 0
    a.assert_not_called()
