"""Unit tests for Upstox HTTP 401/403 refresh behavior."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from brokers.adapters.upstox.http import UpstoxHttpClient
from brokers.domain.exceptions import AuthenticationError
from brokers.resilience.http_client import TokenRefreshSignal


def _mock_response(status_code=200, json_data=None):
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data or {"data": {}}
    resp.text = str(json_data)
    return resp


class TestUpstoxHttp401Retry:
    @patch("brokers.adapters.upstox.http.requests.Session")
    def test_401_triggers_try_refresh_and_retries(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session.headers = {}
        mock_session.request.side_effect = [
            _mock_response(401),
            _mock_response(200, {"data": {"ok": True}}),
        ]
        mock_session_cls.return_value = mock_session

        refresh_called = []

        def refresh_fn():
            refresh_called.append(True)
            return True

        client = UpstoxHttpClient(
            access_token="tok",
            token_refresh_fn=refresh_fn,
        )
        result = client.get("/v2/user/profile")
        assert result == {"data": {"ok": True}}
        assert refresh_called == [True]
        assert mock_session.request.call_count == 2

    @patch("brokers.adapters.upstox.http.requests.Session")
    def test_401_without_refresh_raises(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session.headers = {}
        mock_session.request.return_value = _mock_response(401)
        mock_session_cls.return_value = mock_session

        client = UpstoxHttpClient(access_token="tok")
        with pytest.raises(AuthenticationError):
            client.get("/v2/user/profile")

    def test_handle_response_raises_token_refresh_signal(self):
        client = UpstoxHttpClient(access_token="tok", token_refresh_fn=lambda: True)
        resp = _mock_response(403)
        with pytest.raises(TokenRefreshSignal):
            client._handle_response(resp)
