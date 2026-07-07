"""Mock-based tests for the Dhan provider sub-providers."""

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from tradex.broker.auth import AuthManager, TokenInfo
from tradex.broker.session import SessionManager
from tradex.core.config import RateLimitConfig
from tradex.core.metrics import MetricsCollector
from tradex.core.rate_limiter import RateLimiter
from tradex.domain.account import FundLimits
from tradex.domain.enums import (
    OrderType,
    ProductType,
    Side,
)
from tradex.domain.execution import Order
from tradex.domain.market_data import Quote
from tradex.domain.portfolio import Holding, Position
from tradex.providers.dhan.config import DhanConfig

# ============================================================
# Helpers
# ============================================================


def _make_auth_manager():
    """Create an AuthManager with a valid token."""
    am = AuthManager(auto_refresh=False)
    token = TokenInfo(
        access_token="test_token_123",
        expires_at=9999999999.0,  # far future
    )
    loop = asyncio.new_event_loop()
    loop.run_until_complete(am.set_token(token))
    loop.close()
    return am


def _mock_http_response(status_code=200, data=None, success=True):
    """Create a mock httpx response."""
    resp = AsyncMock()
    resp.status_code = status_code
    body = {"status": "success" if success else "failure"}
    if data is not None:
        body["data"] = data
    if not success:
        body["remarks"] = {"error_code": "DH-905", "error_message": "Validation failed"}
    resp.json = MagicMock(return_value=body)
    resp.raise_for_status = MagicMock()
    return resp


def _mock_client(response):
    """Create a mock httpx.AsyncClient that returns the given response."""
    client = AsyncMock()
    client.headers = MagicMock()
    client.request = AsyncMock(return_value=response)
    client.get = AsyncMock(return_value=response)
    client.post = AsyncMock(return_value=response)
    client.put = AsyncMock(return_value=response)
    client.delete = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


def _make_dhan_config():
    return DhanConfig(
        client_id="test_client",
        access_token="test_token",
        base_url="https://api.dhan.co",
    )


# ============================================================
# DhanExecutionProvider
# ============================================================


class TestDhanExecutionProvider:
    @patch("tradex.providers.dhan.http_client.httpx.AsyncClient")
    def test_place_order_success(self, mock_client_cls):
        from tradex.providers.dhan.execution import DhanExecutionProvider

        config = _make_dhan_config()
        auth = _make_auth_manager()
        session = SessionManager(broker="dhan")

        resp = _mock_http_response(data={"orderId": "ORD_001"})
        mock_client_cls.return_value = _mock_client(resp)

        provider = DhanExecutionProvider(
            config=config,
            auth_manager=auth,
            session=session,
        )

        loop = asyncio.new_event_loop()
        order = loop.run_until_complete(
            provider.place_order(
                security_id="2885",
                exchange_segment="NSE_EQ",
                side=Side.BUY,
                quantity=10,
                order_type=OrderType.LIMIT,
                product_type=ProductType.CNC,
                price=2450.0,
            )
        )
        loop.close()

        assert isinstance(order, Order)
        assert order.order_id == "ORD_001"
        assert order.security_id == "2885"
        assert order.side == Side.BUY
        assert order.quantity == 10

    @patch("tradex.providers.dhan.http_client.httpx.AsyncClient")
    def test_place_order_failure(self, mock_client_cls):
        from tradex.core.errors import ValidationError
        from tradex.providers.dhan.execution import DhanExecutionProvider

        config = _make_dhan_config()
        auth = _make_auth_manager()
        session = SessionManager(broker="dhan")

        resp = _mock_http_response(success=False)
        mock_client_cls.return_value = _mock_client(resp)

        provider = DhanExecutionProvider(
            config=config,
            auth_manager=auth,
            session=session,
        )

        loop = asyncio.new_event_loop()
        with pytest.raises(ValidationError):
            loop.run_until_complete(
                provider.place_order(
                    security_id="2885",
                    exchange_segment="NSE_EQ",
                    side=Side.BUY,
                    quantity=10,
                    order_type=OrderType.LIMIT,
                    product_type=ProductType.CNC,
                    price=2450.0,
                )
            )
        loop.close()

    @patch("tradex.providers.dhan.http_client.httpx.AsyncClient")
    def test_place_order_payload(self, mock_client_cls):
        from tradex.providers.dhan.execution import DhanExecutionProvider

        config = _make_dhan_config()
        auth = _make_auth_manager()
        session = SessionManager(broker="dhan")

        resp = _mock_http_response(data={"orderId": "ORD_002"})
        mock_client_cls.return_value = _mock_client(resp)

        provider = DhanExecutionProvider(
            config=config,
            auth_manager=auth,
            session=session,
        )

        loop = asyncio.new_event_loop()
        loop.run_until_complete(
            provider.place_order(
                security_id="2885",
                exchange_segment="NSE_EQ",
                side=Side.SELL,
                quantity=25,
                order_type=OrderType.MARKET,
                product_type=ProductType.INTRADAY,
                price=0,
                tag="test_tag",
            )
        )
        loop.close()

        # Verify the POST was called with correct payload
        # Check that client.post was called
        mock_client_cls.return_value.__aenter__.return_value.post.assert_called_once()
        call_kwargs = mock_client_cls.return_value.__aenter__.return_value.post.call_args
        payload = call_kwargs.kwargs.get("json", call_kwargs[1].get("json", {}))
        assert payload["securityId"] == "2885"
        assert payload["transactionType"] == "SELL"
        assert payload["quantity"] == 25
        assert payload["correlationID"] == "test_tag"

    @patch("tradex.providers.dhan.http_client.httpx.AsyncClient")
    def test_place_order_with_rate_limiter(self, mock_client_cls):
        from tradex.providers.dhan.execution import DhanExecutionProvider

        config = _make_dhan_config()
        auth = _make_auth_manager()
        session = SessionManager(broker="dhan")
        rl = RateLimiter(RateLimitConfig(per_second=100, per_minute=10000))

        resp = _mock_http_response(data={"orderId": "ORD_003"})
        mock_client_cls.return_value = _mock_client(resp)

        provider = DhanExecutionProvider(
            config=config,
            auth_manager=auth,
            session=session,
            rate_limiter=rl,
        )

        loop = asyncio.new_event_loop()
        order = loop.run_until_complete(
            provider.place_order(
                security_id="2885",
                exchange_segment="NSE_EQ",
                side=Side.BUY,
                quantity=10,
                order_type=OrderType.MARKET,
                product_type=ProductType.INTRADAY,
                price=0,
            )
        )
        loop.close()
        assert order.order_id == "ORD_003"

    @patch("tradex.providers.dhan.http_client.httpx.AsyncClient")
    def test_place_order_with_metrics(self, mock_client_cls):
        from tradex.providers.dhan.execution import DhanExecutionProvider

        config = _make_dhan_config()
        auth = _make_auth_manager()
        session = SessionManager(broker="dhan")
        metrics = MetricsCollector()

        resp = _mock_http_response(data={"orderId": "ORD_004"})
        mock_client_cls.return_value = _mock_client(resp)

        provider = DhanExecutionProvider(
            config=config,
            auth_manager=auth,
            session=session,
            metrics=metrics,
        )

        loop = asyncio.new_event_loop()
        loop.run_until_complete(
            provider.place_order(
                security_id="2885",
                exchange_segment="NSE_EQ",
                side=Side.BUY,
                quantity=10,
                order_type=OrderType.MARKET,
                product_type=ProductType.INTRADAY,
                price=0,
            )
        )
        loop.close()

        assert metrics.get_counter("dhan.orders.placed", exchange="NSE_EQ", side="BUY") == 1

    @patch("tradex.providers.dhan.http_client.httpx.AsyncClient")
    def test_place_order_metrics_on_failure(self, mock_client_cls):
        from tradex.providers.dhan.execution import DhanExecutionProvider

        config = _make_dhan_config()
        auth = _make_auth_manager()
        session = SessionManager(broker="dhan")
        metrics = MetricsCollector()

        resp = _mock_http_response(success=False)
        mock_client_cls.return_value = _mock_client(resp)

        provider = DhanExecutionProvider(
            config=config,
            auth_manager=auth,
            session=session,
            metrics=metrics,
        )

        loop = asyncio.new_event_loop()
        with pytest.raises(Exception):
            loop.run_until_complete(
                provider.place_order(
                    security_id="2885",
                    exchange_segment="NSE_EQ",
                    side=Side.BUY,
                    quantity=10,
                    order_type=OrderType.LIMIT,
                    product_type=ProductType.CNC,
                    price=100,
                )
            )
        loop.close()

        assert metrics.get_counter("dhan.orders.failed", exchange="NSE_EQ") == 1

    @patch("tradex.providers.dhan.http_client.httpx.AsyncClient")
    def test_modify_order(self, mock_client_cls):
        from tradex.providers.dhan.execution import DhanExecutionProvider

        config = _make_dhan_config()
        auth = _make_auth_manager()
        session = SessionManager(broker="dhan")

        # First response for modify, second for get_order
        modify_resp = _mock_http_response(data={"status": "success"})
        order_resp = _mock_http_response(
            data={
                "orderId": "ORD_001",
                "orderStatus": "OPEN",
                "transactionType": "BUY",
                "orderType": "LIMIT",
                "productType": "INTRADAY",
                "quantity": 20,
                "price": 2500,
            }
        )

        mock_instance = AsyncMock()
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_instance.put.return_value = modify_resp
        mock_instance.get.return_value = order_resp
        mock_client_cls.return_value = mock_instance

        provider = DhanExecutionProvider(
            config=config,
            auth_manager=auth,
            session=session,
        )

        loop = asyncio.new_event_loop()
        order = loop.run_until_complete(
            provider.modify_order(
                order_id="ORD_001",
                order_type=OrderType.LIMIT,
                quantity=20,
                price=2500.0,
            )
        )
        loop.close()
        assert order.order_id == "ORD_001"

    @patch("tradex.providers.dhan.http_client.httpx.AsyncClient")
    def test_cancel_order(self, mock_client_cls):
        from tradex.providers.dhan.execution import DhanExecutionProvider

        config = _make_dhan_config()
        auth = _make_auth_manager()
        session = SessionManager(broker="dhan")

        resp = _mock_http_response(data={"status": "success"})
        mock_instance = AsyncMock()
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_instance.delete.return_value = resp
        mock_client_cls.return_value = mock_instance

        provider = DhanExecutionProvider(
            config=config,
            auth_manager=auth,
            session=session,
        )

        loop = asyncio.new_event_loop()
        loop.run_until_complete(provider.cancel_order("ORD_001"))
        loop.close()
        mock_instance.delete.assert_called_once_with("/v2/orders/ORD_001")

    @patch("tradex.providers.dhan.http_client.httpx.AsyncClient")
    def test_get_order(self, mock_client_cls):
        from tradex.providers.dhan.execution import DhanExecutionProvider

        config = _make_dhan_config()
        auth = _make_auth_manager()
        session = SessionManager(broker="dhan")

        resp = _mock_http_response(
            data={
                "orderId": "ORD_100",
                "orderStatus": "TRADED",
                "transactionType": "BUY",
                "orderType": "MARKET",
                "productType": "INTRADAY",
                "quantity": 15,
                "filledQty": 15,
            }
        )
        mock_instance = AsyncMock()
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_instance.get.return_value = resp
        mock_client_cls.return_value = mock_instance

        provider = DhanExecutionProvider(
            config=config,
            auth_manager=auth,
            session=session,
        )

        loop = asyncio.new_event_loop()
        order = loop.run_until_complete(provider.get_order("ORD_100"))
        loop.close()
        assert order.order_id == "ORD_100"
        assert order.filled_quantity == 15

    @patch("tradex.providers.dhan.http_client.httpx.AsyncClient")
    def test_get_orders(self, mock_client_cls):
        from tradex.providers.dhan.execution import DhanExecutionProvider

        config = _make_dhan_config()
        auth = _make_auth_manager()
        session = SessionManager(broker="dhan")

        resp = _mock_http_response(
            data=[
                {
                    "orderId": "O1",
                    "orderStatus": "TRADED",
                    "transactionType": "BUY",
                    "orderType": "MARKET",
                    "productType": "INTRADAY",
                    "quantity": 10,
                },
                {
                    "orderId": "O2",
                    "orderStatus": "PENDING",
                    "transactionType": "SELL",
                    "orderType": "LIMIT",
                    "productType": "CNC",
                    "quantity": 5,
                    "price": 100,
                },
            ]
        )
        mock_instance = AsyncMock()
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_instance.get.return_value = resp
        mock_client_cls.return_value = mock_instance

        provider = DhanExecutionProvider(
            config=config,
            auth_manager=auth,
            session=session,
        )

        loop = asyncio.new_event_loop()
        orders = loop.run_until_complete(provider.get_orders())
        loop.close()
        assert len(orders) == 2
        assert orders[0].order_id == "O1"
        assert orders[1].order_id == "O2"

    @patch("tradex.providers.dhan.http_client.httpx.AsyncClient")
    def test_get_trades(self, mock_client_cls):
        from tradex.providers.dhan.execution import DhanExecutionProvider

        config = _make_dhan_config()
        auth = _make_auth_manager()
        session = SessionManager(broker="dhan")

        resp = _mock_http_response(
            data=[
                {
                    "tradeNo": "T1",
                    "orderId": "O1",
                    "securityId": "2885",
                    "tradingSymbol": "RELIANCE",
                    "transactionType": "BUY",
                    "quantity": 10,
                    "tradedPrice": 2450,
                },
                {
                    "tradeNo": "T2",
                    "orderId": "O2",
                    "securityId": "2886",
                    "tradingSymbol": "TCS",
                    "transactionType": "SELL",
                    "quantity": 5,
                    "tradedPrice": 3500,
                },
            ]
        )
        mock_instance = AsyncMock()
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_instance.get.return_value = resp
        mock_client_cls.return_value = mock_instance

        provider = DhanExecutionProvider(
            config=config,
            auth_manager=auth,
            session=session,
        )

        loop = asyncio.new_event_loop()
        trades = loop.run_until_complete(provider.get_trades(order_id="O1"))
        loop.close()
        assert len(trades) == 1
        assert trades[0].trade_id == "T1"

    def test_error_mapping_auth(self):
        from tradex.core.errors import AuthenticationError, map_provider_error

        err = map_provider_error("DH-901", "Invalid token", provider="dhan")
        assert isinstance(err, AuthenticationError)
        assert not err.retryable

    def test_error_mapping_rate_limit(self):
        from tradex.core.errors import RateLimitError, map_provider_error

        err = map_provider_error("DH-904", "Rate limited", provider="dhan")
        assert isinstance(err, RateLimitError)
        assert err.retryable

    def test_error_mapping_validation(self):
        from tradex.core.errors import ValidationError, map_provider_error

        err = map_provider_error("DH-905", "Invalid params", provider="dhan")
        assert isinstance(err, ValidationError)

    def test_error_mapping_order(self):
        from tradex.core.errors import OrderError, map_provider_error

        err = map_provider_error("DH-906", "Order rejected", provider="dhan")
        assert isinstance(err, OrderError)

    def test_error_mapping_internal(self):
        from tradex.core.errors import InternalError, map_provider_error

        err = map_provider_error("DH-908", "Server error", provider="dhan")
        assert isinstance(err, InternalError)
        assert err.retryable

    def test_error_mapping_network(self):
        from tradex.core.errors import NetworkError, map_provider_error

        err = map_provider_error("DH-909", "Connection timeout", provider="dhan")
        assert isinstance(err, NetworkError)
        assert err.retryable

    def test_error_mapping_ip_whitelist(self):
        from tradex.core.errors import IPWhitelistError, map_provider_error

        err = map_provider_error("DH-911", "IP not whitelisted", provider="dhan")
        assert isinstance(err, IPWhitelistError)

    def test_error_mapping_unknown(self):
        from tradex.core.errors import ProviderError, map_provider_error

        err = map_provider_error("UNKNOWN_CODE", "Something", provider="dhan")
        assert isinstance(err, ProviderError)


# ============================================================
# DhanMarketDataProvider
# ============================================================


class TestDhanMarketDataProvider:
    @patch("tradex.providers.dhan.http_client.httpx.AsyncClient")
    def test_get_quote_success(self, mock_client_cls):
        from tradex.providers.dhan.market import DhanMarketDataProvider

        config = _make_dhan_config()
        auth = _make_auth_manager()

        resp = _mock_http_response(
            data={
                "NSE_EQ": {
                    "2885": {
                        "last_price": 2450.50,
                        "average_price": 2440,
                        "top_bid_price": 2449,
                        "top_bid_quantity": 100,
                        "top_ask_price": 2451,
                        "top_ask_quantity": 50,
                        "volume": 123456,
                        "ohlc": {"open": 2430, "high": 2460, "low": 2420, "close": 2435},
                        "upper_circuit": 2700,
                        "lower_circuit": 2200,
                        "net_change": 15.5,
                    }
                }
            }
        )
        mock_instance = AsyncMock()
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_instance.post.return_value = resp
        mock_client_cls.return_value = mock_instance

        provider = DhanMarketDataProvider(config=config, auth_manager=auth)

        loop = asyncio.new_event_loop()
        quote = loop.run_until_complete(provider.get_quote("2885", "NSE_EQ"))
        loop.close()

        assert isinstance(quote, Quote)
        assert quote.last_price == Decimal("2450.50")
        assert quote.security_id == "2885"

    @patch("tradex.providers.dhan.http_client.httpx.AsyncClient")
    def test_get_ohlcv(self, mock_client_cls):
        from tradex.providers.dhan.market import DhanMarketDataProvider

        config = _make_dhan_config()
        auth = _make_auth_manager()

        resp = _mock_http_response(
            data={
                "timestamp": [1700000000, 1700086400],
                "open": [100, 101],
                "high": [110, 112],
                "low": [95, 99],
                "close": [105, 108],
                "volume": [1000, 1200],
            }
        )
        mock_instance = AsyncMock()
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_instance.post.return_value = resp
        mock_client_cls.return_value = mock_instance

        provider = DhanMarketDataProvider(config=config, auth_manager=auth)

        loop = asyncio.new_event_loop()
        bars = loop.run_until_complete(
            provider.get_ohlcv(
                security_id="2885",
                exchange="NSE_EQ",
                instrument_type="EQUITY",
                start_date="2024-01-01",
                end_date="2024-01-31",
            )
        )
        loop.close()
        assert len(bars) == 2
        assert bars[0].open == Decimal("100")

    @patch("tradex.providers.dhan.http_client.httpx.AsyncClient")
    def test_get_minute_data(self, mock_client_cls):
        from tradex.providers.dhan.market import DhanMarketDataProvider

        config = _make_dhan_config()
        auth = _make_auth_manager()

        resp = _mock_http_response(
            data={
                "timestamp": [1700000000],
                "open": [100],
                "high": [105],
                "low": [99],
                "close": [103],
                "volume": [500],
            }
        )
        mock_instance = AsyncMock()
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_instance.post.return_value = resp
        mock_client_cls.return_value = mock_instance

        provider = DhanMarketDataProvider(config=config, auth_manager=auth)

        loop = asyncio.new_event_loop()
        bars = loop.run_until_complete(
            provider.get_minute_data(
                security_id="2885",
                exchange="NSE_EQ",
                instrument_type="EQUITY",
                start_date="2024-01-01",
                end_date="2024-01-01",
                interval=5,
            )
        )
        loop.close()
        assert len(bars) == 1

    @patch("tradex.providers.dhan.http_client.httpx.AsyncClient")
    def test_get_option_chain(self, mock_client_cls):
        from tradex.providers.dhan.market import DhanMarketDataProvider

        config = _make_dhan_config()
        auth = _make_auth_manager()

        payload = {
            "last_price": 24500,
            "oc": {
                "24000": {
                    "ce": {"security_id": "50001", "last_price": 600, "oi": 10000},
                    "pe": {"security_id": "50002", "last_price": 100, "oi": 15000},
                },
                "25000": {
                    "ce": {"security_id": "50003", "last_price": 100, "oi": 5000},
                    "pe": {"security_id": "50004", "last_price": 600, "oi": 20000},
                },
            },
        }
        resp = _mock_http_response(data=payload)
        mock_instance = AsyncMock()
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_instance.post.return_value = resp
        mock_client_cls.return_value = mock_instance

        provider = DhanMarketDataProvider(config=config, auth_manager=auth)

        loop = asyncio.new_event_loop()
        chain = loop.run_until_complete(
            provider.get_option_chain(
                underlying_security_id="13",
                exchange="IDX_I",
                expiry="2025-03-27",
            )
        )
        loop.close()

        assert len(chain.strikes) == 2
        assert chain.spot_price == Decimal("24500")

    @patch("tradex.providers.dhan.http_client.httpx.AsyncClient")
    def test_get_expiry_list(self, mock_client_cls):
        from tradex.providers.dhan.market import DhanMarketDataProvider

        config = _make_dhan_config()
        auth = _make_auth_manager()

        resp = _mock_http_response(data=["2025-03-27", "2025-04-03", "2025-04-10"])
        mock_instance = AsyncMock()
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_instance.get.return_value = resp
        mock_client_cls.return_value = mock_instance

        provider = DhanMarketDataProvider(config=config, auth_manager=auth)

        loop = asyncio.new_event_loop()
        expiry_list = loop.run_until_complete(provider.get_expiry_list("13", "IDX_I"))
        loop.close()
        assert len(expiry_list) == 3
        assert "2025-03-27" in expiry_list

    @patch("tradex.providers.dhan.http_client.httpx.AsyncClient")
    def test_get_depth(self, mock_client_cls):
        from tradex.providers.dhan.market import DhanMarketDataProvider

        config = _make_dhan_config()
        auth = _make_auth_manager()

        resp = _mock_http_response(
            data={
                "NSE_EQ": {
                    "2885": {
                        "last_price": 2450,
                        "top_bid_price": 2449,
                        "top_bid_quantity": 100,
                        "top_ask_price": 2451,
                        "top_ask_quantity": 50,
                        "ohlc": {"open": 2440, "high": 2460, "low": 2430, "close": 2445},
                        "upper_circuit": 2700,
                        "lower_circuit": 2200,
                    }
                }
            }
        )
        mock_instance = AsyncMock()
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_instance.post.return_value = resp
        mock_client_cls.return_value = mock_instance

        provider = DhanMarketDataProvider(config=config, auth_manager=auth)

        loop = asyncio.new_event_loop()
        depth = loop.run_until_complete(provider.get_depth("2885", "NSE_EQ"))
        loop.close()
        assert depth.security_id == "2885"

    @patch("tradex.providers.dhan.http_client.httpx.AsyncClient")
    def test_rate_limiter_called(self, mock_client_cls):
        from tradex.providers.dhan.market import DhanMarketDataProvider

        config = _make_dhan_config()
        auth = _make_auth_manager()
        rl = AsyncMock()
        rl.acquire = AsyncMock(return_value=0.0)

        resp = _mock_http_response(
            data={
                "NSE_EQ": {
                    "2885": {
                        "last_price": 2450,
                        "ohlc": {"open": 2440, "high": 2460, "low": 2430, "close": 2445},
                        "upper_circuit": 2700,
                        "lower_circuit": 2200,
                    }
                }
            }
        )
        mock_instance = AsyncMock()
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_instance.post.return_value = resp
        mock_client_cls.return_value = mock_instance

        provider = DhanMarketDataProvider(
            config=config,
            auth_manager=auth,
            rate_limiter=rl,
        )

        loop = asyncio.new_event_loop()
        loop.run_until_complete(provider.get_quote("2885", "NSE_EQ"))
        loop.close()
        rl.acquire.assert_called()


# ============================================================
# DhanPortfolioProvider
# ============================================================


class TestDhanPortfolioProvider:
    @patch("tradex.providers.dhan.http_client.httpx.AsyncClient")
    def test_get_holdings(self, mock_client_cls):
        from tradex.providers.dhan.portfolio import DhanPortfolioProvider

        config = _make_dhan_config()
        auth = _make_auth_manager()

        resp = _mock_http_response(
            data=[
                {
                    "securityId": "2885",
                    "tradingSymbol": "RELIANCE",
                    "exchange": "NSE_EQ",
                    "totalQty": 50,
                    "availableQty": 50,
                    "avgCostPrice": 2450,
                },
                {
                    "securityId": "1153",
                    "tradingSymbol": "TCS",
                    "exchange": "NSE_EQ",
                    "totalQty": 20,
                    "availableQty": 20,
                    "avgCostPrice": 3500,
                },
            ]
        )
        mock_instance = AsyncMock()
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_instance.get.return_value = resp
        mock_client_cls.return_value = mock_instance

        provider = DhanPortfolioProvider(config=config, auth_manager=auth)

        loop = asyncio.new_event_loop()
        holdings = loop.run_until_complete(provider.get_holdings())
        loop.close()

        assert len(holdings) == 2
        assert isinstance(holdings[0], Holding)
        assert holdings[0].security_id == "2885"
        assert holdings[1].trading_symbol == "TCS"

    @patch("tradex.providers.dhan.http_client.httpx.AsyncClient")
    def test_get_positions(self, mock_client_cls):
        from tradex.providers.dhan.portfolio import DhanPortfolioProvider

        config = _make_dhan_config()
        auth = _make_auth_manager()

        resp = _mock_http_response(
            data=[
                {
                    "securityId": "49081",
                    "tradingSymbol": "NIFTY28MAR25FUT",
                    "exchangeSegment": "NSE_FNO",
                    "productType": "INTRADAY",
                    "positionType": "LONG",
                    "buyAvg": 24500,
                    "buyQty": 75,
                    "netQty": 75,
                    "unrealizedProfit": 1500,
                },
                {
                    "securityId": "49082",
                    "tradingSymbol": "NIFTY28MAR25FUT",
                    "positionType": "CLOSED",
                    "netQty": 0,
                    "realizedProfit": 3000,
                },
            ]
        )
        mock_instance = AsyncMock()
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_instance.get.return_value = resp
        mock_client_cls.return_value = mock_instance

        provider = DhanPortfolioProvider(config=config, auth_manager=auth)

        loop = asyncio.new_event_loop()
        positions = loop.run_until_complete(provider.get_positions())
        loop.close()

        assert len(positions) == 2
        assert isinstance(positions[0], Position)
        assert positions[0].is_open
        assert not positions[1].is_open

    @patch("tradex.providers.dhan.http_client.httpx.AsyncClient")
    def test_get_fund_limits(self, mock_client_cls):
        from tradex.providers.dhan.portfolio import DhanPortfolioProvider

        config = _make_dhan_config()
        auth = _make_auth_manager()

        resp = _mock_http_response(
            data={
                "availabelBalance": 100000,
                "collateralAmount": 50000,
                "blockedPayoutAmount": 5000,
            }
        )
        mock_instance = AsyncMock()
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_instance.get.return_value = resp
        mock_client_cls.return_value = mock_instance

        provider = DhanPortfolioProvider(config=config, auth_manager=auth)

        loop = asyncio.new_event_loop()
        fl = loop.run_until_complete(provider.get_fund_limits())
        loop.close()

        assert isinstance(fl, FundLimits)
        assert fl.available_balance == Decimal("100000")
        assert fl.net_available == Decimal("145000")

    @patch("tradex.providers.dhan.http_client.httpx.AsyncClient")
    def test_calculate_margin(self, mock_client_cls):
        from tradex.providers.dhan.portfolio import DhanPortfolioProvider

        config = _make_dhan_config()
        auth = _make_auth_manager()

        resp = _mock_http_response(
            data={
                "totalMargin": 100000,
                "spanMargin": 80000,
                "exposureMargin": 20000,
                "availableBalance": 150000,
                "brokerage": 50,
                "leverage": 5,
            }
        )
        mock_instance = AsyncMock()
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_instance.post.return_value = resp
        mock_client_cls.return_value = mock_instance

        provider = DhanPortfolioProvider(config=config, auth_manager=auth)

        loop = asyncio.new_event_loop()
        margin = loop.run_until_complete(
            provider.calculate_margin(
                security_id="49081",
                exchange="NSE_FNO",
                side=Side.BUY,
                quantity=75,
                product_type=ProductType.MARGIN,
                price=24500,
            )
        )
        loop.close()

        assert margin["total_margin"] == 100000
        assert margin["sufficient"] is True
        assert margin["brokerage"] == 50

    @patch("tradex.providers.dhan.http_client.httpx.AsyncClient")
    def test_rate_limiter_called(self, mock_client_cls):
        from tradex.providers.dhan.portfolio import DhanPortfolioProvider

        config = _make_dhan_config()
        auth = _make_auth_manager()
        rl = AsyncMock()
        rl.acquire = AsyncMock(return_value=0.0)

        resp = _mock_http_response(data=[])
        mock_instance = AsyncMock()
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_instance.get.return_value = resp
        mock_client_cls.return_value = mock_instance

        provider = DhanPortfolioProvider(
            config=config,
            auth_manager=auth,
            rate_limiter=rl,
        )

        loop = asyncio.new_event_loop()
        loop.run_until_complete(provider.get_holdings())
        loop.close()
        rl.acquire.assert_called()


# ============================================================
# DhanAuthProvider
# ============================================================


class TestDhanAuthProvider:
    @patch("tradex.providers.dhan.http_client.httpx.AsyncClient")
    def test_connect_success(self, mock_client_cls):
        from tradex.providers.dhan.auth import DhanAuthProvider

        config = _make_dhan_config()
        auth_manager = AuthManager()
        session = SessionManager(broker="dhan")

        resp = _mock_http_response(
            data={
                "dhanClientId": "test_client",
                "fullName": "Test User",
                "activeSegment": "NSE_EQ",
            }
        )
        mock_instance = AsyncMock()
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_instance.get.return_value = resp
        mock_client_cls.return_value = mock_instance

        provider = DhanAuthProvider(
            config=config,
            auth_manager=auth_manager,
            session=session,
        )

        loop = asyncio.new_event_loop()
        loop.run_until_complete(provider.connect())
        loop.close()

        assert auth_manager.is_authenticated
        assert session.is_connected

    def test_disconnect(self):
        from tradex.providers.dhan.auth import DhanAuthProvider

        config = _make_dhan_config()
        auth_manager = AuthManager()
        session = SessionManager(broker="dhan")

        provider = DhanAuthProvider(
            config=config,
            auth_manager=auth_manager,
            session=session,
        )

        loop = asyncio.new_event_loop()
        loop.run_until_complete(provider.disconnect())
        loop.close()

        assert not auth_manager.is_authenticated
        assert session.status.value == "disconnected"

    def test_token_info_properties(self):
        import time

        token = TokenInfo(
            access_token="abc",
            expires_at=time.time() + 100,
        )
        assert not token.is_expired
        assert token.expires_in > 0

    def test_token_needs_refresh(self):
        import time

        token = TokenInfo(
            access_token="abc",
            expires_at=time.time() + 600,  # 600s from now, > 300 threshold
        )
        assert not token.needs_refresh

    def test_token_needs_refresh_soon(self):
        import time

        token = TokenInfo(
            access_token="abc",
            expires_at=time.time() + 60,  # 60s from now, < 300 threshold
        )
        assert token.needs_refresh

    def test_token_expired(self):
        import time

        token = TokenInfo(
            access_token="abc",
            expires_at=time.time() - 10,
        )
        assert token.is_expired

    def test_session_state(self):
        from tradex.broker.auth import SessionState

        state = SessionState()
        assert not state.is_valid

        token = TokenInfo(access_token="abc", expires_at=9999999999)
        state = SessionState(authenticated=True, token=token)
        assert state.is_valid
