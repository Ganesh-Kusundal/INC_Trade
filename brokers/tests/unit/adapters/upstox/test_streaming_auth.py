"""Unit tests for Upstox streaming token provider and feed authorization."""

from __future__ import annotations

from unittest.mock import MagicMock

from brokers.adapters.upstox.feed_authorizer import UpstoxFeedAuthorizer
from brokers.adapters.upstox.streaming import UpstoxStreaming


class TestUpstoxStreamingToken:
    def test_get_ws_headers_empty_for_authorized_url(self):
        tokens = ["tok-a", "tok-b"]
        idx = [0]

        def provider():
            return tokens[idx[0]]

        streaming = UpstoxStreaming(access_token=provider)
        assert streaming._get_ws_headers() == {}

    def test_update_access_token(self):
        streaming = UpstoxStreaming(access_token="old")
        streaming.update_access_token("new")
        assert streaming._token_provider() == "new"

    def test_get_ws_url_uses_feed_authorizer(self):
        http = MagicMock()
        authorizer = UpstoxFeedAuthorizer(http)
        authorizer.authorize_market_data_v3 = MagicMock(
            return_value="wss://authorized.example/feed"
        )
        streaming = UpstoxStreaming(
            access_token="tok", feed_authorizer=authorizer
        )
        assert streaming._get_ws_url() == "wss://authorized.example/feed"

    def test_resolve_key_uses_index_mapping(self):
        streaming = UpstoxStreaming(access_token="tok")
        assert streaming._resolve_key("NIFTY", "INDEX") == "NSE_INDEX|Nifty 50"
