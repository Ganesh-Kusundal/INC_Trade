from __future__ import annotations

from unittest.mock import MagicMock, patch

from brokers.adapters.upstox.auth.config import UpstoxConnectionSettings
from brokers.adapters.upstox.gateway import UpstoxGateway


class TestUpstoxGateway:
    @patch("brokers.adapters.upstox.gateway.UpstoxStreaming")
    def test_instantiation_with_token(self, mock_streaming_class):
        gw = UpstoxGateway(access_token="test-access-token")
        assert gw.auth.get_token() == "test-access-token"
        assert gw.orders is not None
        assert gw.market_data is not None
        assert gw.portfolio is not None
        assert gw.instruments is not None
        assert gw.historical is not None
        assert gw.streaming is not None
        gw.close()

    @patch("brokers.adapters.upstox.gateway.UpstoxStreaming")
    def test_instantiation_with_settings(self, mock_streaming_class):
        s = UpstoxConnectionSettings(
            client_id="my-client",
            access_token="token-abc",
            environment="LIVE",
        )
        gw = UpstoxGateway(settings=s)
        assert gw.auth.get_token() == "token-abc"
        gw.close()

    @patch("brokers.adapters.upstox.gateway.UpstoxStreaming")
    @patch("brokers.adapters.upstox.auth.totp_scheduler.TotpRefreshScheduler")
    def test_auto_refresh_scheduler_start(self, mock_scheduler_class, mock_streaming_class):
        s = UpstoxConnectionSettings(
            client_id="my-client",
            access_token="token-abc",
            auth_mode="TOTP",
            mobile="9876543210",
            pin="123456",
            totp_secret="SECRET",
            environment="LIVE",
        )
        mock_scheduler = MagicMock()
        mock_scheduler_class.return_value = mock_scheduler

        gw = UpstoxGateway(settings=s, auto_refresh=True)
        assert gw._scheduler is not None
        mock_scheduler.start.assert_called_once()
        gw.close()
        mock_scheduler.stop.assert_called_once()

    @patch("brokers.adapters.upstox.gateway.UpstoxStreaming")
    def test_news_retrieval(self, mock_streaming_class):
        gw = UpstoxGateway(access_token="test-access-token")
        assert gw.news is not None

        # Mock http client get response
        gw._client.get = MagicMock(return_value={"data": [{"id": 1, "title": "News 1"}]})
        res = gw.news.get_news(symbol="RELIANCE")
        assert len(res) == 1
        assert res[0].headline == "News 1"
        gw._client.get.assert_called_once()

    @patch("brokers.adapters.upstox.gateway.UpstoxStreaming")
    def test_stream_depth(self, mock_streaming_class):
        gw = UpstoxGateway(access_token="test-access-token")
        mock_ws = mock_streaming_class.return_value
        mock_ws.is_connected = False

        on_depth = MagicMock()
        handle = gw.stream_depth("RELIANCE", "NSE", "DEPTH_30", on_depth)

        assert handle is not None
        assert mock_ws.mode == "full_d30"
        assert mock_ws.on_depth == on_depth
        mock_ws.subscribe.assert_called_once_with("RELIANCE", "NSE")
        mock_ws.start.assert_called_once()

        handle.stop()
        mock_ws.unsubscribe.assert_called_once_with("RELIANCE", "NSE")

