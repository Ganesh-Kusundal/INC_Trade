"""Unit tests for Upstox compatibility gateway."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from brokers.adapters.upstox.compat_gateway import UpstoxCompatibilityGateway
from brokers.adapters.upstox.gateway import UpstoxGateway


class TestUpstoxCompatGateway:
    @patch("brokers.adapters.upstox.gateway.UpstoxStreaming")
    def test_delegates_ltp(self, mock_streaming):
        gw = UpstoxGateway(access_token="tok")
        compat = UpstoxCompatibilityGateway(gw)
        gw.market_data.ltp = MagicMock(return_value=100)
        assert compat.ltp("RELIANCE") == 100
        gw.close()

    @patch("brokers.adapters.upstox.gateway.UpstoxStreaming")
    def test_orderbook_alias(self, mock_streaming):
        gw = UpstoxGateway(access_token="tok")
        compat = UpstoxCompatibilityGateway(gw)
        gw.orders.get_orderbook = MagicMock(return_value=[])
        assert compat.orderbook() == []
        gw.close()
