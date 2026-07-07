"""Unit tests for DhanProvider — mocked HTTP client, no network IO.

Tests cover:
  - Market data: get_quote, get_ltp, get_depth
  - Historical: get_history
  - Instrument search & resolve
  - Execution: place_order, cancel_order, modify_order
  - Portfolio: get_positions, get_balance, get_orders, get_trades, get_holdings
  - Lifecycle: connect/disconnect
  - Identity: broker_id, capabilities, is_connected
  - Instrument resolver wiring
  - Error handling: HttpError, ProviderError
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from brokers.domain.enums import Exchange, OrderStatus, OrderType, ProductType, Side
from brokers.domain.exceptions import ProviderError
from brokers.domain.requests import ModifyOrderRequest, OrderRequest
from brokers.infrastructure.http_client import HttpError
from brokers.dhan.dhan_provider import DhanProvider


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_client() -> MagicMock:
    """Create a mock DhanHttpClient."""
    client = MagicMock()
    client.client_id = "test_client_123"
    return client


@pytest.fixture
def provider(mock_client: MagicMock) -> DhanProvider:
    """Create a DhanProvider with a mock client injected."""
    p = DhanProvider(
        client_id="test_client_123",
        access_token="test_token",
        instruments={"RELIANCE:NSE": "3456"},
    )
    p._client = mock_client
    # Mock streaming feeds to avoid WebSocket connections
    p._market_feed = MagicMock()
    p._market_feed.is_running = True
    p._market_feed._orchestrator = MagicMock()
    p._market_feed.subscribe = AsyncMock()
    p._market_feed.unsubscribe = AsyncMock()
    p._market_feed.stop = AsyncMock()
    p._order_feed = MagicMock()
    p._order_feed.is_running = True
    p._order_feed._orchestrator = MagicMock()
    p._order_feed.stop = AsyncMock()
    p._depth_feed = MagicMock()
    p._depth_feed.is_running = True
    p._depth_feed.subscribe = AsyncMock()
    p._depth_feed.unsubscribe = AsyncMock()
    p._depth_feed.stop = AsyncMock()
    return p


@pytest.fixture
def provider_no_instruments(mock_client: MagicMock) -> DhanProvider:
    """Create a DhanProvider with no pre-populated instruments dict."""
    p = DhanProvider(
        client_id="test_client_123",
        access_token="test_token",
    )
    p._client = mock_client
    # Mock streaming feeds to avoid WebSocket connections
    p._market_feed = MagicMock()
    p._market_feed.is_running = True
    p._market_feed._orchestrator = MagicMock()
    p._market_feed.subscribe = AsyncMock()
    p._market_feed.unsubscribe = AsyncMock()
    p._market_feed.stop = AsyncMock()
    p._order_feed = MagicMock()
    p._order_feed.is_running = True
    p._order_feed._orchestrator = MagicMock()
    p._order_feed.stop = AsyncMock()
    p._depth_feed = MagicMock()
    p._depth_feed.is_running = True
    p._depth_feed.subscribe = AsyncMock()
    p._depth_feed.unsubscribe = AsyncMock()
    p._depth_feed.stop = AsyncMock()
    return p


# ── Identity tests ──────────────────────────────────────────────────────────


class TestDhanProviderIdentity:
    def test_broker_id(self, provider: DhanProvider) -> None:
        assert provider.broker_id == "dhan"

    def test_capabilities(self, provider: DhanProvider) -> None:
        caps = provider.capabilities
        assert caps.broker_id == "dhan"

    def test_is_connected_default_false(self, provider: DhanProvider) -> None:
        assert provider.is_connected is False

    @pytest.mark.asyncio
    async def test_connect_sets_connected(self, provider: DhanProvider) -> None:
        await provider.connect()
        assert provider.is_connected is True

    @pytest.mark.asyncio
    async def test_disconnect_clears_connected(self, provider: DhanProvider) -> None:
        await provider.connect()
        assert provider.is_connected is True
        await provider.disconnect()
        assert provider.is_connected is False

    def test_default_account(self, provider: DhanProvider) -> None:
        account = provider.default_account
        assert account is not None


# ── Market data tests ───────────────────────────────────────────────────────


class TestDhanProviderMarketData:
    @pytest.mark.asyncio
    async def test_get_quote(
        self, provider: DhanProvider, mock_client: MagicMock
    ) -> None:
        from brokers.domain.instrument import Instrument

        mock_client.get_quote.return_value = {
            "data": {
                "NSE_EQ": {
                    "3456": {
                        "last_price": "2550.50",
                        "ohlc": {"open": "2540", "high": "2560", "low": "2530", "close": "2545"},
                        "volume": 100000,
                        "net_change": "5.50",
                    }
                }
            }
        }

        inst = Instrument(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            provider=provider,  # type: ignore[arg-type]
            security_id="3456",
        )
        quote = await provider.get_quote(inst)

        assert quote.symbol == "RELIANCE"
        assert quote.ltp == Decimal("2550.50")
        assert quote.open == Decimal("2540")
        assert quote.high == Decimal("2560")
        assert quote.low == Decimal("2530")
        assert quote.close == Decimal("2545")
        assert quote.volume == 100000

    @pytest.mark.asyncio
    async def test_get_quote_raises_on_missing_data(
        self, provider: DhanProvider, mock_client: MagicMock
    ) -> None:
        from brokers.domain.instrument import Instrument

        mock_client.get_quote.return_value = {"data": {"NSE_EQ": {}}}

        inst = Instrument(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            provider=provider,  # type: ignore[arg-type]
            security_id="3456",
        )
        with pytest.raises(ProviderError, match="No quote data"):
            await provider.get_quote(inst)

    @pytest.mark.asyncio
    async def test_get_ltp(
        self, provider: DhanProvider, mock_client: MagicMock
    ) -> None:
        from brokers.domain.instrument import Instrument

        mock_client.get_ltp.return_value = {
            "data": {
                "NSE_EQ": {
                    "3456": {"last_price": "2550.50"},
                }
            }
        }

        inst = Instrument(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            provider=provider,  # type: ignore[arg-type]
            security_id="3456",
        )
        ltp = await provider.get_ltp(inst)
        assert ltp == Decimal("2550.50")

    @pytest.mark.asyncio
    async def test_get_depth(
        self, provider: DhanProvider, mock_client: MagicMock
    ) -> None:
        from brokers.domain.instrument import Instrument

        mock_client.get_quote.return_value = {
            "data": {
                "NSE_EQ": {
                    "3456": {
                        "last_price": "2550.50",
                        "depth": {
                            "buy": [
                                {"price": "2550.45", "quantity": 100, "orders": 5},
                                {"price": "2550.40", "quantity": 200, "orders": 3},
                            ],
                            "sell": [
                                {"price": "2550.55", "quantity": 150, "orders": 4},
                                {"price": "2550.60", "quantity": 300, "orders": 2},
                            ],
                        },
                    }
                }
            }
        }

        inst = Instrument(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            provider=provider,  # type: ignore[arg-type]
            security_id="3456",
        )
        depth = await provider.get_depth(inst)

        assert depth.symbol == "RELIANCE"
        assert len(depth.bids) == 2
        assert depth.bids[0].price == Decimal("2550.45")
        assert depth.bids[0].quantity == 100
        assert len(depth.asks) == 2
        assert depth.asks[0].price == Decimal("2550.55")

    @pytest.mark.asyncio
    async def test_get_quote_uses_instruments_dict_for_security_id(
        self, provider: DhanProvider, mock_client: MagicMock
    ) -> None:
        from brokers.domain.instrument import Instrument

        mock_client.get_quote.return_value = {
            "data": {
                "NSE_EQ": {
                    "3456": {"last_price": "100", "ohlc": {}},
                }
            }
        }

        inst = Instrument(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            provider=provider,  # type: ignore[arg-type]
            # No security_id — should resolve from instruments dict
        )
        await provider.get_quote(inst)

        # Verify the client was called with the resolved security_id
        call_args = mock_client.get_quote.call_args
        assert call_args[0][1] == [3456]  # security_ids list


# ── Historical data tests ──────────────────────────────────────────────────


class TestDhanProviderHistory:
    @pytest.mark.asyncio
    async def test_get_history_daily(
        self, provider: DhanProvider, mock_client: MagicMock
    ) -> None:
        from datetime import date

        from brokers.domain.instrument import Instrument

        mock_client.post.return_value = {
            "data": {
                "ohlc": [
                    ["2026-07-01", "2540", "2560", "2530", "2550", 100000],
                    ["2026-07-02", "2550", "2570", "2545", "2565", 120000],
                ]
            }
        }

        inst = Instrument(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            provider=provider,  # type: ignore[arg-type]
            security_id="3456",
        )
        series = await provider.get_history(
            inst,
            timeframe="1D",
            from_date=date(2026, 7, 1),
            to_date=date(2026, 7, 2),
        )

        assert series.symbol == "RELIANCE"
        assert series.exchange == "NSE"
        assert series.timeframe == "1D"
        assert len(series.bars) == 2
        assert series.bars[0].open == Decimal("2540")
        assert series.bars[0].close == Decimal("2550")
        assert series.bars[0].volume == 100000
        assert series.bars[1].open == Decimal("2550")
        assert series.bars[1].close == Decimal("2565")

    @pytest.mark.asyncio
    async def test_get_history_dict_format(
        self, provider: DhanProvider, mock_client: MagicMock
    ) -> None:
        from datetime import date

        from brokers.domain.instrument import Instrument

        mock_client.post.return_value = {
            "data": {
                "candles": [
                    {"date": "2026-07-01", "open": "100", "high": "110", "low": "95", "close": "105", "volume": 5000},
                ]
            }
        }

        inst = Instrument(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            provider=provider,  # type: ignore[arg-type]
            security_id="3456",
        )
        series = await provider.get_history(
            inst,
            timeframe="1D",
            from_date=date(2026, 7, 1),
            to_date=date(2026, 7, 2),
        )

        assert len(series.bars) == 1
        assert series.bars[0].open == Decimal("100")
        assert series.bars[0].close == Decimal("105")

    @pytest.mark.asyncio
    async def test_get_history_empty(
        self, provider: DhanProvider, mock_client: MagicMock
    ) -> None:
        from datetime import date

        from brokers.domain.instrument import Instrument

        mock_client.post.return_value = {"data": {}}

        inst = Instrument(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            provider=provider,  # type: ignore[arg-type]
            security_id="3456",
        )
        series = await provider.get_history(
            inst,
            timeframe="1D",
            from_date=date(2026, 7, 1),
            to_date=date(2026, 7, 2),
        )

        assert len(series.bars) == 0


# ── Instrument search & resolve tests ──────────────────────────────────────


class TestDhanProviderInstruments:
    @pytest.mark.asyncio
    async def test_search_instruments(self, provider: DhanProvider) -> None:
        results = await provider.search_instruments("RELI")
        assert len(results) == 1
        assert results[0].symbol == "RELIANCE"
        assert results[0].security_id == "3456"

    @pytest.mark.asyncio
    async def test_search_instruments_no_match(self, provider: DhanProvider) -> None:
        results = await provider.search_instruments("NONEXISTENT")
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_get_instruments_all(self, provider: DhanProvider) -> None:
        results = await provider.get_instruments()
        assert len(results) == 1
        assert results[0].symbol == "RELIANCE"

    @pytest.mark.asyncio
    async def test_get_instruments_by_exchange(self, provider: DhanProvider) -> None:
        results = await provider.get_instruments("NSE")
        assert len(results) == 1

        results = await provider.get_instruments("BSE")
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_resolve_instrument(self, provider: DhanProvider) -> None:
        inst = await provider.resolve_instrument("RELIANCE", "NSE")
        assert inst.symbol == "RELIANCE"
        assert inst.exchange == Exchange.NSE
        assert inst.security_id == "3456"

    @pytest.mark.asyncio
    async def test_resolve_instrument_not_in_dict(
        self, provider: DhanProvider
    ) -> None:
        inst = await provider.resolve_instrument("TCS", "NSE")
        assert inst.symbol == "TCS"
        assert inst.security_id == "TCS"  # Falls back to symbol


# ── Execution tests ────────────────────────────────────────────────────────


class TestDhanProviderExecution:
    @pytest.mark.asyncio
    async def test_place_order_success(
        self, provider: DhanProvider, mock_client: MagicMock
    ) -> None:
        mock_client.place_order.return_value = {
            "data": {"orderId": "dhan_order_001"},
        }

        request = OrderRequest(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            side=Side.BUY,
            quantity=10,
            order_type=OrderType.MARKET,
            product_type=ProductType.INTRADAY,
        )
        response = await provider.place_order(request)

        assert response.success is True
        assert response.order_id == "dhan_order_001"
        assert response.status == OrderStatus.OPEN
        mock_client.place_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_place_order_http_error(
        self, provider: DhanProvider, mock_client: MagicMock
    ) -> None:
        mock_client.place_order.side_effect = HttpError("Server error")

        request = OrderRequest(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            side=Side.BUY,
            quantity=10,
        )
        response = await provider.place_order(request)

        assert response.success is False
        assert "Server error" in response.message
        assert response.error_code == "DHAN_HTTP_ERROR"

    @pytest.mark.asyncio
    async def test_place_order_generic_error(
        self, provider: DhanProvider, mock_client: MagicMock
    ) -> None:
        mock_client.place_order.side_effect = ValueError("Unexpected error")

        request = OrderRequest(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            side=Side.BUY,
            quantity=10,
        )
        response = await provider.place_order(request)

        assert response.success is False
        assert "Unexpected error" in response.message
        assert response.error_code == "INTERNAL_ERROR"

    @pytest.mark.asyncio
    async def test_cancel_order_success(
        self, provider: DhanProvider, mock_client: MagicMock
    ) -> None:
        mock_client.cancel_order.return_value = {"status": "success"}

        response = await provider.cancel_order("dhan_order_001")

        assert response.success is True
        assert response.order_id == "dhan_order_001"
        assert response.status == OrderStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_order_failure(
        self, provider: DhanProvider, mock_client: MagicMock
    ) -> None:
        mock_client.cancel_order.return_value = {
            "status": "failed",
            "errorMessage": "Order already executed",
            "errorCode": "ALREADY_EXECUTED",
        }

        response = await provider.cancel_order("dhan_order_001")

        assert response.success is False
        assert "Order already executed" in response.message
        assert response.error_code == "ALREADY_EXECUTED"

    @pytest.mark.asyncio
    async def test_cancel_order_http_error(
        self, provider: DhanProvider, mock_client: MagicMock
    ) -> None:
        mock_client.cancel_order.side_effect = HttpError("Network error")

        response = await provider.cancel_order("dhan_order_001")

        assert response.success is False
        assert response.error_code == "DHAN_HTTP_ERROR"

    @pytest.mark.asyncio
    async def test_modify_order_success(
        self, provider: DhanProvider, mock_client: MagicMock
    ) -> None:
        mock_client.modify_order.return_value = {"status": "success"}

        request = ModifyOrderRequest(
            order_id="dhan_order_001",
            quantity=20,
            price=Decimal("2550"),
        )
        response = await provider.modify_order(request)

        assert response.success is True
        assert response.order_id == "dhan_order_001"
        mock_client.modify_order.assert_called_once_with("dhan_order_001", {
            "quantity": 20,
            "price": Decimal("2550"),
        })

    @pytest.mark.asyncio
    async def test_modify_order_error_code(
        self, provider: DhanProvider, mock_client: MagicMock
    ) -> None:
        mock_client.modify_order.return_value = {
            "errorCode": "MODIFY_FAILED",
            "errorMessage": "Cannot modify filled order",
        }

        request = ModifyOrderRequest(order_id="dhan_order_001", quantity=20)
        response = await provider.modify_order(request)

        assert response.success is False
        assert "Cannot modify filled order" in response.message

    @pytest.mark.asyncio
    async def test_cancel_order_dhan_style_success(
        self, provider: DhanProvider, mock_client: MagicMock
    ) -> None:
        """Dhan cancel response has NO top-level status; it uses orderId /
        orderStatus.  Success must be detected via those fields (#1)."""
        mock_client.cancel_order.return_value = {
            "orderId": "dhan_order_001",
            "orderStatus": "CANCELLED",
        }

        response = await provider.cancel_order("dhan_order_001")

        assert response.success is True
        assert response.order_id == "dhan_order_001"
        assert response.status == OrderStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_modify_order_includes_required_fields(
        self, provider: DhanProvider, mock_client: MagicMock
    ) -> None:
        """modify_order must resolve the instrument and include securityId /
        exchangeSegment / transactionType, not just the change-set (#2).

        ModifyOrderRequest is frozen and currently has no instrument field;
        the provider reads it via getattr so it works once the domain owner
        extends the request.  Here we drive the resolver path directly and
        then assert the full payload is sent.
        """
        from types import SimpleNamespace

        from brokers.domain.instrument import Instrument

        instrument = Instrument(
            symbol="RELIANCE", exchange=Exchange.NSE, provider=provider,  # type: ignore[arg-type]
            security_id="3456",
        )
        # Fake request exposing the (future) instrument attribute.
        request = SimpleNamespace(
            order_id="dhan_order_001",
            instrument=instrument,
            symbol=None,
            exchange=None,
            quantity=20,
            price=Decimal("2550"),
            trigger_price=None,
            order_type=OrderType.LIMIT,
            validity=None,
            product_type=None,
        )
        sid = provider._resolve_modify_security_id(request)  # type: ignore[arg-type]
        assert sid == "3456"

        response = await provider.modify_order(request)  # type: ignore[arg-type]

        assert response.success is True
        mock_client.modify_order.assert_called_once()
        _oid, payload = mock_client.modify_order.call_args.args
        assert payload["securityId"] == "3456"
        assert payload["exchangeSegment"] == "NSE_EQ"
        assert payload["quantity"] == 20
        assert payload["price"] == Decimal("2550")

    @pytest.mark.asyncio
    async def test_place_order_uses_resolver_when_instruments_dict_empty(
        self, mock_client: MagicMock
    ) -> None:
        """Verify place_order resolves security_id via resolver, not just _instruments dict."""
        from brokers.common.instrument_resolver import ResolvedInstrument
        from brokers.domain.instrument import Instrument

        mock_resolver = MagicMock()
        mock_resolver.resolve.return_value = ResolvedInstrument(
            symbol="TCS",
            exchange=Exchange.NSE,
            broker_id="9999",
            segment="NSE_EQ",
            lot_size=1,
            tick_size=Decimal("0.05"),
            trading_symbol="TCS",
        )

        mock_client.place_order.return_value = {
            "data": {"orderId": "dhan_order_002"},
        }

        # Provider with NO _instruments dict — only resolver
        p = DhanProvider(
            client_id="test", access_token="tok", resolver=mock_resolver
        )
        p._client = mock_client

        # Instrument without security_id (normal user flow)
        inst = Instrument(
            symbol="TCS",
            exchange=Exchange.NSE,
            provider=p,
            # No security_id — must be resolved via resolver
        )
        request = OrderRequest(
            symbol="TCS",
            exchange=Exchange.NSE,
            side=Side.BUY,
            quantity=5,
            instrument=inst,
        )
        response = await p.place_order(request)

        assert response.success is True
        # Verify the resolver was consulted
        mock_resolver.resolve.assert_called_once_with("TCS", Exchange.NSE)
        # Verify the payload was built with the resolved numeric security_id
        call_args = mock_client.place_order.call_args
        payload = call_args[1]["json"] if "json" in call_args[1] else call_args[0][0]
        assert payload["securityId"] == "9999"


# ── Portfolio tests ────────────────────────────────────────────────────────


class TestDhanProviderPortfolio:
    @pytest.mark.asyncio
    async def test_get_positions(
        self, provider: DhanProvider, mock_client: MagicMock
    ) -> None:
        mock_client.get_positions.return_value = {
            "data": [
                {
                    "tradingSymbol": "RELIANCE",
                    "exchangeSegment": "NSE_EQ",
                    "netQuantity": 10,
                    "buyAveragePrice": "2500",
                    "lastPrice": "2550",
                    "unrealizedPnl": "500",
                    "productType": "INTRADAY",
                }
            ]
        }

        positions = await provider.get_positions()
        assert len(positions) == 1
        assert positions[0].symbol == "RELIANCE"
        assert positions[0].quantity == 10
        assert positions[0].average_price == Decimal("2500")

    @pytest.mark.asyncio
    async def test_get_positions_empty(
        self, provider: DhanProvider, mock_client: MagicMock
    ) -> None:
        mock_client.get_positions.return_value = {"data": []}

        positions = await provider.get_positions()
        assert len(positions) == 0

    @pytest.mark.asyncio
    async def test_get_balance(
        self, provider: DhanProvider, mock_client: MagicMock
    ) -> None:
        mock_client.get_funds.return_value = {
            "data": {
                "availabelBalance": "100000",
                "sodLimit": "100000",
                "utilizedAmount": "25000",
                "withdrawableBalance": "75000",
            }
        }

        balance = await provider.get_balance()
        assert balance.available_balance == Decimal("100000")
        assert balance.sod_limit == Decimal("100000")
        assert balance.used_margin == Decimal("25000")
        assert balance.withdrawable_balance == Decimal("75000")

    @pytest.mark.asyncio
    async def test_get_orders(
        self, provider: DhanProvider, mock_client: MagicMock
    ) -> None:
        mock_client.get_orderbook.return_value = {
            "data": [
                {
                    "orderId": "dhan_001",
                    "tradingSymbol": "RELIANCE",
                    "exchangeSegment": "NSE_EQ",
                    "transactionType": "BUY",
                    "quantity": 10,
                    "orderType": "MARKET",
                    "productType": "INTRADAY",
                    "orderStatus": "FILLED",
                    "filledQty": 10,
                    "avgPrice": "2550",
                }
            ]
        }

        orders = await provider.get_orders()
        assert len(orders) == 1

    @pytest.mark.asyncio
    async def test_get_trades(
        self, provider: DhanProvider, mock_client: MagicMock
    ) -> None:
        mock_client.get_trades.return_value = {
            "data": [
                {
                    "tradeId": "trade_001",
                    "orderId": "dhan_001",
                    "tradingSymbol": "RELIANCE",
                    "exchangeSegment": "NSE_EQ",
                    "transactionType": "BUY",
                    "tradedQty": 10,
                    "tradedPrice": "2550",
                    "productType": "INTRADAY",
                }
            ]
        }

        trades = await provider.get_trades()
        assert len(trades) == 1
        assert trades[0].trade_id == "trade_001"
        assert trades[0].price == Decimal("2550")

    @pytest.mark.asyncio
    async def test_get_holdings(
        self, provider: DhanProvider, mock_client: MagicMock
    ) -> None:
        mock_client.get_holdings.return_value = {
            "data": [
                {
                    "tradingSymbol": "RELIANCE",
                    "exchangeSegment": "NSE_EQ",
                    "totalQty": 100,
                    "avgCostPrice": "2000",
                    "lastTradedPrice": "2550",
                }
            ]
        }

        holdings = await provider.get_holdings()
        assert len(holdings) == 1
        assert holdings[0].symbol == "RELIANCE"
        assert holdings[0].quantity == 100
        assert holdings[0].average_price == Decimal("2000")


# ── Streaming tests ────────────────────────────────────────────────────────


class TestDhanProviderStreaming:
    @pytest.mark.asyncio
    async def test_subscribe_quotes_returns_subscription(
        self, provider: DhanProvider
    ) -> None:
        from brokers.domain.instrument import Instrument
        from brokers.domain.values import Subscription

        inst = Instrument(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            provider=provider,  # type: ignore[arg-type]
            security_id="3456",
        )
        sub = await provider.subscribe_quotes([inst])
        assert isinstance(sub, Subscription)
        assert sub.is_active

    @pytest.mark.asyncio
    async def test_subscribe_depth_returns_subscription(
        self, provider: DhanProvider
    ) -> None:
        from brokers.domain.instrument import Instrument
        from brokers.domain.values import Subscription

        inst = Instrument(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            provider=provider,  # type: ignore[arg-type]
            security_id="3456",
        )
        sub = await provider.subscribe_depth([inst])
        assert isinstance(sub, Subscription)

    @pytest.mark.asyncio
    async def test_subscribe_orders_returns_subscription(
        self, provider: DhanProvider
    ) -> None:
        from brokers.domain.values import Subscription

        sub = await provider.subscribe_orders()
        assert isinstance(sub, Subscription)


# ── Resolver wiring tests ──────────────────────────────────────────────────


class TestDhanProviderResolver:
    @pytest.mark.asyncio
    async def test_resolve_instrument_with_resolver(self) -> None:
        from brokers.common.instrument_resolver import ResolvedInstrument

        mock_resolver = MagicMock()
        mock_resolver.resolve.return_value = ResolvedInstrument(
            symbol="TCS",
            exchange=Exchange.NSE,
            broker_id="12345",
            segment="NSE_EQ",
            lot_size=1,
            tick_size=Decimal("0.05"),
            trading_symbol="TCS",
        )

        p = DhanProvider(client_id="test", access_token="tok", resolver=mock_resolver)
        inst = await p.resolve_instrument("TCS", "NSE")

        assert inst.security_id == "12345"
        assert inst.lot_size == 1
        assert inst.trading_symbol == "TCS"
        mock_resolver.resolve.assert_called_once()

    @pytest.mark.asyncio
    async def test_resolve_instrument_resolver_not_found(self) -> None:
        from brokers.common.instrument_resolver import InstrumentNotFoundError

        mock_resolver = MagicMock()
        mock_resolver.resolve.side_effect = InstrumentNotFoundError("UNKNOWN", "NSE", "dhan")

        p = DhanProvider(client_id="test", access_token="tok", resolver=mock_resolver)
        inst = await p.resolve_instrument("UNKNOWN", "NSE")

        # Falls back gracefully
        assert inst.symbol == "UNKNOWN"
        assert inst.security_id != ""  # Gets a fallback security_id (symbol)

    @pytest.mark.asyncio
    async def test_search_instruments_with_resolver(self) -> None:
        from brokers.common.instrument_resolver import ResolvedInstrument

        mock_resolver = MagicMock()
        mock_resolver.search.return_value = [
            ResolvedInstrument(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                broker_id="3456",
                segment="NSE_EQ",
                lot_size=1,
                trading_symbol="RELIANCE",
            ),
            ResolvedInstrument(
                symbol="RELIANCE",
                exchange=Exchange.BSE,
                broker_id="3457",
                segment="BSE_EQ",
                lot_size=1,
                trading_symbol="RELIANCE",
            ),
        ]

        p = DhanProvider(client_id="test", access_token="tok", resolver=mock_resolver)
        results = await p.search_instruments("RELI")

        assert len(results) == 2
        assert results[0].symbol == "RELIANCE"
        assert results[0].security_id == "3456"
        mock_resolver.search.assert_called_once_with("RELI", limit=20)

    @pytest.mark.asyncio
    async def test_get_quote_uses_resolver_for_security_id(self) -> None:
        from brokers.common.instrument_resolver import ResolvedInstrument
        from brokers.domain.instrument import Instrument

        mock_resolver = MagicMock()
        mock_resolver.resolve.return_value = ResolvedInstrument(
            symbol="TCS",
            exchange=Exchange.NSE,
            broker_id="9999",
            segment="NSE_EQ",
        )

        mock_client = MagicMock()
        mock_client.get_quote.return_value = {
            "data": {"NSE_EQ": {"9999": {"last_price": "3500", "ohlc": {}}}}
        }

        p = DhanProvider(
            client_id="test", access_token="tok", resolver=mock_resolver
        )
        p._client = mock_client

        inst = Instrument(
            symbol="TCS",
            exchange=Exchange.NSE,
            provider=p,  # type: ignore[arg-type]
            # No security_id — should use resolver
        )
        quote = await p.get_quote(inst)

        assert quote.ltp == Decimal("3500")
        mock_resolver.resolve.assert_called_once()


# ── Segment routing tests ────────────────────────────────────────────────────


class TestDhanSegmentRouting:
    """Verify Exchange → Dhan segment string mapping."""

    def test_currency_segment_routing(self) -> None:
        from brokers.dhan.dhan_provider import _segment_for

        assert _segment_for(Exchange.CURRENCY) == "NSE_CURRENCY"

    def test_bse_fno_segment_routing(self) -> None:
        from brokers.dhan.dhan_provider import _segment_for

        assert _segment_for(Exchange.BSE_FNO) == "BSE_FNO"

    def test_nfo_still_maps_to_nse_fno(self) -> None:
        from brokers.dhan.dhan_provider import _segment_for

        assert _segment_for(Exchange.NFO) == "NSE_FNO"

    def test_mcx_still_maps_to_mcx_comm(self) -> None:
        from brokers.dhan.dhan_provider import _segment_for

        assert _segment_for(Exchange.MCX) == "MCX_COMM"


# ── Product-type validation tests ────────────────────────────────────────────


class TestDhanProductTypeValidation:
    """Verify product-type validation per Dhan segment rules."""

    def test_rejects_cnc_for_fno(self) -> None:
        from brokers.dhan.mapper import validate_product_type

        with pytest.raises(ValueError, match="not allowed"):
            validate_product_type("NSE_FNO", "CNC")

    def test_rejects_mtf_for_fno(self) -> None:
        from brokers.dhan.mapper import validate_product_type

        with pytest.raises(ValueError, match="not allowed"):
            validate_product_type("NSE_FNO", "MTF")

    def test_rejects_cnc_for_commodity(self) -> None:
        from brokers.dhan.mapper import validate_product_type

        with pytest.raises(ValueError, match="not allowed"):
            validate_product_type("MCX_COMM", "CNC")

    def test_rejects_mtf_for_currency(self) -> None:
        from brokers.dhan.mapper import validate_product_type

        with pytest.raises(ValueError, match="not allowed"):
            validate_product_type("NSE_CURRENCY", "MTF")

    def test_accepts_intraday_for_fno(self) -> None:
        from brokers.dhan.mapper import validate_product_type

        validate_product_type("NSE_FNO", "INTRADAY")  # Should not raise

    def test_accepts_margin_for_fno(self) -> None:
        from brokers.dhan.mapper import validate_product_type

        validate_product_type("NSE_FNO", "MARGIN")  # Should not raise

    def test_accepts_cnc_for_equity(self) -> None:
        from brokers.dhan.mapper import validate_product_type

        validate_product_type("NSE_EQ", "CNC")  # Should not raise

    def test_accepts_mtf_for_equity(self) -> None:
        from brokers.dhan.mapper import validate_product_type

        validate_product_type("BSE_EQ", "MTF")  # Should not raise

    def test_accepts_intraday_for_bse_fno(self) -> None:
        from brokers.dhan.mapper import validate_product_type

        validate_product_type("BSE_FNO", "INTRADAY")  # Should not raise

    def test_rejects_cnc_for_bse_fno(self) -> None:
        from brokers.dhan.mapper import validate_product_type

        with pytest.raises(ValueError, match="not allowed"):
            validate_product_type("BSE_FNO", "CNC")

    def test_unknown_segment_skips_validation(self) -> None:
        from brokers.dhan.mapper import validate_product_type

        validate_product_type("UNKNOWN_SEG", "CNC")  # Should not raise

    def test_build_order_payload_validates_product_type(self) -> None:
        from brokers.dhan.mapper import DhanMapper

        request = OrderRequest(
            symbol="NIFTY",
            exchange=Exchange.NFO,
            side=Side.BUY,
            quantity=50,
            product_type=ProductType.CNC,  # Invalid for NSE_FNO
        )
        with pytest.raises(ValueError, match="not allowed"):
            DhanMapper.build_order_payload(request, "13", "NSE_FNO", "client123")
