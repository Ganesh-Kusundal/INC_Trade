"""Tests for DhanAdapter — direct sub-adapter composition without gateway.

Verifies:
- Adapter construction and connect/disconnect lifecycle
- Delegation of quote/ltp/depth/orders to sub-adapters
- Property accessors (broker_id, is_connected, max_levels)
- Error handling when not connected
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from brokers.adapters.dhan.adapter import DhanAdapter


class TestDhanAdapterLifecycle:
    """Adapter construction and connect/disconnect."""

    def test_constructor_with_minimal_params(self) -> None:
        """Adapter can be created with just client_id and access_token."""
        adapter = DhanAdapter(client_id="test123", access_token="token_abc")
        assert adapter.broker_id == "dhan"
        assert not adapter.is_connected
        assert adapter.max_levels == 200

    def test_constructor_with_all_params(self) -> None:
        """Adapter can be created with all optional params."""
        adapter = DhanAdapter(
            client_id="test123",
            access_token="token_abc",
            pin="1234",
            totp_secret="secret",
            allow_live_orders=False,
            auto_refresh=False,
        )
        assert adapter.broker_id == "dhan"
        assert not adapter.is_connected

    def test_connect_success(self) -> None:
        """connect() initialises all sub-adapters."""
        adapter = DhanAdapter(client_id="test123", access_token="token_abc")

        with (
            patch("brokers.adapters.dhan.adapter.DhanAuth") as mock_auth,
            patch("brokers.adapters.dhan.adapter.DhanInstrumentResolver") as mock_resolver,
            patch("brokers.adapters.dhan.adapter.create_dhan_http_client") as mock_http,
            patch("brokers.adapters.dhan.adapter.DhanConnectionManager") as mock_conn_mgr,
            patch("brokers.adapters.dhan.adapter.DhanMarketData") as mock_md,
            patch("brokers.adapters.dhan.adapter.DhanOrders") as mock_orders,
            patch("brokers.adapters.dhan.adapter.DhanHistorical") as mock_hist,
            patch("brokers.adapters.dhan.adapter.DhanStreaming") as mock_stream,
        ):
            # Configure mocks
            mock_auth_instance = MagicMock()
            mock_auth_instance.is_authenticated.return_value = True
            mock_auth_instance.get_token.return_value = "token_abc"
            mock_auth.return_value = mock_auth_instance

            mock_resolver_instance = MagicMock()
            mock_resolver.return_value = mock_resolver_instance

            mock_http_instance = MagicMock()
            mock_http.return_value = mock_http_instance

            mock_md_instance = MagicMock()
            mock_md.return_value = mock_md_instance

            mock_orders_instance = MagicMock()
            mock_orders.return_value = mock_orders_instance

            mock_hist_instance = MagicMock()
            mock_hist.return_value = mock_hist_instance

            mock_stream_instance = MagicMock()
            mock_stream.return_value = mock_stream_instance

            adapter.connect()

        assert adapter.is_connected
        mock_auth.assert_called_once()
        mock_resolver.assert_called_once()
        mock_http.assert_called_once_with(
            client_id="test123",
            access_token="token_abc",
        )
        mock_md.assert_called_once()
        mock_orders.assert_called_once()
        mock_hist.assert_called_once()
        mock_stream.assert_called_once()

    def test_connect_auth_failure(self) -> None:
        """connect() raises RuntimeError if auth fails."""
        adapter = DhanAdapter(client_id="test123")

        with patch("brokers.adapters.dhan.adapter.DhanAuth") as mock_auth:
            mock_auth_instance = MagicMock()
            mock_auth_instance.is_authenticated.return_value = False
            mock_auth.return_value = mock_auth_instance

            with pytest.raises(RuntimeError, match="could not acquire a token"):
                adapter.connect()

        assert not adapter.is_connected

    def test_disconnect(self) -> None:
        """disconnect() closes all sub-adapters."""
        adapter = DhanAdapter(client_id="test123", access_token="token_abc")

        with (
            patch("brokers.adapters.dhan.adapter.DhanAuth") as mock_auth,
            patch("brokers.adapters.dhan.adapter.DhanInstrumentResolver") as mock_resolver,
            patch("brokers.adapters.dhan.adapter.create_dhan_http_client") as mock_http,
            patch("brokers.adapters.dhan.adapter.DhanConnectionManager") as mock_conn_mgr,
            patch("brokers.adapters.dhan.adapter.DhanMarketData") as mock_md,
            patch("brokers.adapters.dhan.adapter.DhanOrders") as mock_orders,
            patch("brokers.adapters.dhan.adapter.DhanHistorical") as mock_hist,
            patch("brokers.adapters.dhan.adapter.DhanStreaming") as mock_stream,
        ):
            mock_auth_instance = MagicMock()
            mock_auth_instance.is_authenticated.return_value = True
            mock_auth_instance.get_token.return_value = "token_abc"
            mock_auth.return_value = mock_auth_instance

            mock_resolver_instance = MagicMock()
            mock_resolver.return_value = mock_resolver_instance

            mock_http_instance = MagicMock()
            mock_http.return_value = mock_http_instance

            mock_stream_instance = MagicMock()
            mock_stream.return_value = mock_stream_instance

            mock_md.return_value = MagicMock()
            mock_orders.return_value = MagicMock()
            mock_hist.return_value = MagicMock()

            adapter.connect()
            assert adapter.is_connected

            adapter.disconnect()

        assert not adapter.is_connected
        mock_stream_instance.stop.assert_called_once()
        mock_http_instance.close.assert_called_once()

    def test_operations_raise_when_not_connected(self) -> None:
        """All provider methods raise RuntimeError if not connected."""
        adapter = DhanAdapter(client_id="test123", access_token="token_abc")

        with pytest.raises(RuntimeError, match="not connected"):
            adapter.quote("RELIANCE", "NSE")

        with pytest.raises(RuntimeError, match="not connected"):
            adapter.ltp("RELIANCE", "NSE")

        with pytest.raises(RuntimeError, match="not connected"):
            adapter.depth("RELIANCE", "NSE")

        with pytest.raises(RuntimeError, match="not connected"):
            adapter.get_candles("RELIANCE", "NSE", None, None, "1D")


class TestDhanAdapterMarketData:
    """Market data delegation to sub-adapters."""

    def test_quote_delegates_to_market_data(self) -> None:
        """quote() delegates to DhanMarketData.quote()."""
        adapter = DhanAdapter(client_id="test123", access_token="token_abc")
        self._mock_connect(adapter)

        adapter._market_data.quote.return_value = MagicMock()
        result = adapter.quote("RELIANCE", "NSE")

        adapter._market_data.quote.assert_called_once_with("RELIANCE", "NSE")
        assert result is not None

    def test_ltp_delegates_to_market_data(self) -> None:
        """ltp() delegates to DhanMarketData.ltp()."""
        adapter = DhanAdapter(client_id="test123", access_token="token_abc")
        self._mock_connect(adapter)

        adapter._market_data.ltp.return_value = Decimal("2850.50")
        result = adapter.ltp("RELIANCE", "NSE")

        adapter._market_data.ltp.assert_called_once_with("RELIANCE", "NSE")
        assert result == Decimal("2850.50")

    def test_depth_delegates_to_market_data(self) -> None:
        """depth() delegates to DhanMarketData.depth()."""
        adapter = DhanAdapter(client_id="test123", access_token="token_abc")
        self._mock_connect(adapter)

        adapter._market_data.depth.return_value = MagicMock()
        result = adapter.depth("RELIANCE", "NSE")

        adapter._market_data.depth.assert_called_once_with("RELIANCE", "NSE")
        assert result is not None

    @staticmethod
    def _mock_connect(adapter: DhanAdapter) -> None:
        """Bypass real connect and set up mocks directly."""
        adapter._auth = MagicMock()
        adapter._auth.get_token.return_value = "token_abc"
        adapter._resolver = MagicMock()
        adapter._http_client = MagicMock()
        adapter._market_data = MagicMock()
        adapter._orders = MagicMock()
        adapter._historical = MagicMock()
        adapter._streaming = MagicMock()
        adapter._conn_mgr = MagicMock()
        adapter._connected = True


class TestDhanAdapterOrders:
    """Order delegation to sub-adapters."""

    def test_place_order_delegates_to_orders(self) -> None:
        """place_order() delegates to DhanOrders.place_order()."""
        adapter = DhanAdapter(client_id="test123", access_token="token_abc")
        TestDhanAdapterMarketData._mock_connect(adapter)

        adapter._orders.place_order.return_value = MagicMock()
        result = adapter.place_order("RELIANCE", "NSE", "BUY", 10)

        adapter._orders.place_order.assert_called_once()
        assert result is not None

    def test_cancel_order_delegates_to_orders(self) -> None:
        """cancel_order() delegates to DhanOrders.cancel_order()."""
        adapter = DhanAdapter(client_id="test123", access_token="token_abc")
        TestDhanAdapterMarketData._mock_connect(adapter)

        adapter._orders.cancel_order.return_value = MagicMock()
        result = adapter.cancel_order("order-123")

        adapter._orders.cancel_order.assert_called_once_with("order-123")
        assert result is not None


class TestDhanAdapterHistorical:
    """Historical data delegation to sub-adapters."""

    def test_get_candles_delegates_to_historical(self) -> None:
        """get_candles() delegates to DhanHistorical.get_historical_candles()."""
        from datetime import datetime

        adapter = DhanAdapter(client_id="test123", access_token="token_abc")
        TestDhanAdapterMarketData._mock_connect(adapter)

        start = datetime(2025, 1, 1)
        end = datetime(2025, 1, 31)

        adapter._historical.get_historical_candles.return_value = []
        result = adapter.get_candles("RELIANCE", "NSE", start, end, "1D")

        adapter._historical.get_historical_candles.assert_called_once_with(
            symbol="RELIANCE",
            exchange="NSE",
            start_time=start,
            end_time=end,
            resolution="1D",
        )
        assert result == []


class TestDhanAdapterStreaming:
    """Streaming subscription delegation."""

    def test_subscribe_requires_symbol_and_exchange(self) -> None:
        """subscribe() requires instrument with symbol and exchange."""
        adapter = DhanAdapter(client_id="test123", access_token="token_abc")
        TestDhanAdapterMarketData._mock_connect(adapter)

        callback = MagicMock()
        with pytest.raises(ValueError, match="must have symbol and exchange"):
            adapter.subscribe(MagicMock(symbol=None, exchange=None), callback)

    def test_subscribe_starts_streaming(self) -> None:
        """subscribe() starts streaming if not already connected."""
        adapter = DhanAdapter(client_id="test123", access_token="token_abc")
        TestDhanAdapterMarketData._mock_connect(adapter)

        adapter._streaming.is_connected = False

        instrument = MagicMock()
        instrument.symbol = "RELIANCE"
        instrument.exchange = "NSE"

        callback = MagicMock()
        handle = adapter.subscribe(instrument, callback)

        adapter._streaming.start.assert_called_once()
        adapter._streaming.subscribe.assert_called_once_with("RELIANCE", "NSE")
        assert handle is not None

    def test_unsubscribe_delegates_to_streaming(self) -> None:
        """unsubscribe() delegates to DhanStreaming.unsubscribe()."""
        adapter = DhanAdapter(client_id="test123", access_token="token_abc")
        TestDhanAdapterMarketData._mock_connect(adapter)

        instrument = MagicMock()
        instrument.symbol = "RELIANCE"
        instrument.exchange = "NSE"

        adapter.unsubscribe(instrument)
        adapter._streaming.unsubscribe.assert_called_once_with("RELIANCE", "NSE")
