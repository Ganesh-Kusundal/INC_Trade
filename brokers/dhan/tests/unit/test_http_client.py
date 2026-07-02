"""Unit tests for DhanHttpClient."""

from unittest.mock import MagicMock, patch

import pytest

from brokers.dhan.exceptions import AuthenticationError, DhanError, RateLimitError
from brokers.dhan.http_client import DhanHttpClient


def _make_client() -> DhanHttpClient:
    """Create a DhanHttpClient with a mocked session (no real HTTP calls)."""
    with patch("brokers.dhan.http_client.requests.Session") as mock_cls:
        mock_session = MagicMock()
        mock_session.headers = {}
        mock_cls.return_value = mock_session
        client = DhanHttpClient("CID", "TOKEN")
    return client


def _mock_response(status_code: int, json_data=None, text: str = "") -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    if json_data is not None:
        resp.json.return_value = json_data
    else:
        resp.json.side_effect = ValueError("no json")
    return resp


def test_response_unwrapping():
    client = _make_client()
    resp = _mock_response(200, {"status": "success", "data": {"key": "val"}})
    client._session.request.return_value = resp

    result = client.post("/orders", {"symbol": "RELIANCE"})
    assert result == {"status": "success", "data": {"key": "val"}}


def test_auth_error_on_401():
    client = _make_client()
    client._session.request.return_value = _mock_response(401, text="Unauthorized")

    with pytest.raises(AuthenticationError, match="401"):
        client.get("/holdings")


def test_rate_limit_error_on_429():
    client = _make_client()
    client._session.request.return_value = _mock_response(429, text="Too Many Requests")

    with pytest.raises(RateLimitError, match="429"):
        client.post("/marketfeed/quote", {"ids": []})


def test_dhan_error_on_500():
    client = _make_client()
    client._session.request.return_value = _mock_response(500, text="Internal Server Error")

    with pytest.raises(DhanError, match="500"):
        client.get("/positions")


def test_failure_status_unwrapped():
    client = _make_client()
    resp = _mock_response(200, {"status": "failure", "remarks": "Invalid symbol"})
    client._session.request.return_value = resp

    with pytest.raises(DhanError, match="Invalid symbol"):
        client.post("/orders", {"symbol": "BAD"})


def test_update_token():
    client = _make_client()
    assert client.access_token == "TOKEN"

    client.update_token("NEW_TOKEN")
    assert client.access_token == "NEW_TOKEN"
    assert client._session.headers["access-token"] == "NEW_TOKEN"
