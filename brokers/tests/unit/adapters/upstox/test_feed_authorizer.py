"""Unit tests for UpstoxFeedAuthorizer."""

from __future__ import annotations

from unittest.mock import MagicMock

from brokers.adapters.upstox.feed_authorizer import UpstoxFeedAuthorizer


class TestUpstoxFeedAuthorizer:
    def test_authorize_market_data_v3_extracts_url(self):
        http = MagicMock()
        http.get.return_value = {
            "data": {"authorized_redirect_uri": "wss://ws-auth.example/feed"}
        }
        auth = UpstoxFeedAuthorizer(http)
        assert auth.authorize_market_data_v3() == "wss://ws-auth.example/feed"

    def test_authorize_portfolio_stream(self):
        http = MagicMock()
        http.get.return_value = {
            "data": {"redirect_uri": "wss://ws-auth.example/portfolio"}
        }
        auth = UpstoxFeedAuthorizer(http)
        url = auth.authorize_portfolio_stream()
        assert url == "wss://ws-auth.example/portfolio"
        http.get.assert_called_once()
        call_kwargs = http.get.call_args
        assert "update_types" in (call_kwargs.kwargs.get("params") or {})
