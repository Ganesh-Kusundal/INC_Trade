from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from brokers.upstox.auth.config import UpstoxConnectionSettings
from brokers.upstox.auth.exceptions import UpstoxApiError
from brokers.upstox.auth.http import UpstoxHttpClient


def test_http_client_injects_bearer_and_algo_name():
    session = MagicMock()
    resp = MagicMock()
    resp.status_code = 200
    resp.text = '{"status": "success", "data": {}}'
    session.request.return_value = resp
    settings = UpstoxConnectionSettings(client_id="CID", access_token="", algo_name="my-algo")
    client = UpstoxHttpClient(token_provider=lambda: "TOK", settings=settings, session=session)
    client.get_json("https://api.upstox.com/v2/user/profile")
    headers = session.request.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer TOK"
    assert headers["X-Algo-Name"] == "my-algo"
    assert session.request.call_args.kwargs["method"] == "GET"


def test_http_client_raises_on_4xx():
    session = MagicMock()
    resp = MagicMock()
    resp.status_code = 401
    resp.text = "unauthorized"
    session.request.return_value = resp
    settings = UpstoxConnectionSettings(client_id="CID")
    client = UpstoxHttpClient(token_provider=lambda: "TOK", settings=settings, session=session)
    with pytest.raises(UpstoxApiError) as excinfo:
        client.get_json("https://api.upstox.com/v2/user/profile")
    assert excinfo.value.status_code == 401


def test_http_client_raises_on_error_status_in_body():
    session = MagicMock()
    resp = MagicMock()
    resp.status_code = 200
    resp.text = '{"status": "error", "errors": [{"message": "bad price"}]}'
    resp.json.return_value = {
        "status": "error",
        "errors": [{"message": "bad price"}],
    }
    session.request.return_value = resp
    settings = UpstoxConnectionSettings(client_id="CID")
    client = UpstoxHttpClient(token_provider=lambda: "TOK", settings=settings, session=session)
    with pytest.raises(UpstoxApiError) as excinfo:
        client.get_json("https://api.upstox.com/v2/order/place")
    assert "bad price" in str(excinfo.value)


def test_http_client_does_not_send_algo_header_when_blank():
    session = MagicMock()
    resp = MagicMock()
    resp.status_code = 200
    resp.text = '{"status": "success", "data": {}}'
    session.request.return_value = resp
    settings = UpstoxConnectionSettings(client_id="CID", algo_name="")
    client = UpstoxHttpClient(token_provider=lambda: "TOK", settings=settings, session=session)
    client.get_json("https://api.upstox.com/v2/user/profile")
    headers = session.request.call_args.kwargs["headers"]
    assert "X-Algo-Name" not in headers


def test_enable_retry_removed():
    """enable_retry parameter was removed (no callers, pre-v1.0)."""
    session = MagicMock()
    settings = UpstoxConnectionSettings(client_id="CID")
    with pytest.raises(TypeError):
        UpstoxHttpClient(
            token_provider=lambda: "TOK",
            settings=settings,
            session=session,
            enable_retry=True,
        )


def test_read_circuit_breaker_does_not_block_write():
    from brokers.common.resilience.circuit_breaker import CircuitState
    from brokers.common.resilience.errors import CircuitBreakerOpenError

    session = MagicMock()
    settings = UpstoxConnectionSettings(client_id="CID")
    client = UpstoxHttpClient(
        token_provider=lambda: "TOK",
        settings=settings,
        session=session,
    )
    assert client._read_circuit_breaker is not None
    assert client._write_circuit_breaker is not None
    for _ in range(12):
        client._read_circuit_breaker.on_failure()
    assert client._read_circuit_breaker.state == CircuitState.OPEN

    resp = MagicMock()
    resp.status_code = 200
    resp.text = '{"status": "success", "data": {}}'
    session.request.return_value = resp

    client.post_json(
        "https://api.upstox.com/v2/order/place",
        {"quantity": 1},
    )
    session.request.assert_called_once()
    assert client._write_circuit_breaker.state != CircuitState.OPEN

    with pytest.raises(CircuitBreakerOpenError):
        client.get_json("https://api.upstox.com/v2/market-quote/ltp")
