"""Unit tests for UpstoxProvider — mocked HTTP client, no network IO.

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
from brokers.upstox.upstox_provider import UpstoxProvider


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_client() -> MagicMock:
    """Create a mock UpstoxHttpClient."""
    return MagicMock()


@pytest.fixture
def provider(mock_client: MagicMock) -> UpstoxProvider:
    """Create an UpstoxProvider with a mock client injected."""
    p = UpstoxProvider(
        access_token="test_token",
        instruments={"RELIANCE:NSE": "NSE_EQ|INE002A01018"},
    )
    p._client = mock_client
    # Mock streaming feeds to avoid WebSocket connections
    p._market_feed = MagicMock()
    p._market_feed.is_running = True
    p._market_feed._orchestrator = MagicMock()
    p._market_feed.subscribe = AsyncMock()
    p._market_feed.unsubscribe = AsyncMock()
    p._market_feed.stop = AsyncMock()
    p._portfolio_stream = MagicMock()
    p._portfolio_stream.is_running = True
    p._portfolio_stream._orchestrator = MagicMock()
    p._portfolio_stream.stop = AsyncMock()
    return p


# ── Identity tests ──────────────────────────────────────────────────────────


class TestUpstoxProviderIdentity:
    def test_broker_id(self, provider: UpstoxProvider) -> None:
        assert provider.broker_id == "upstox"

    def test_capabilities(self, provider: UpstoxProvider) -> None:
        caps = provider.capabilities
        assert caps.broker_id == "upstox"

    def test_is_connected_default_false(self, provider: UpstoxProvider) -> None:
        assert provider.is_connected is False

    @pytest.mark.asyncio
    async def test_connect_sets_connected(self, provider: UpstoxProvider) -> None:
        await provider.connect()
        assert provider.is_connected is True

    @pytest.mark.asyncio
    async def test_disconnect_clears_connected(self, provider: UpstoxProvider) -> None:
        await provider.connect()
        await provider.disconnect()
        assert provider.is_connected is False

    def test_default_account(self, provider: UpstoxProvider) -> None:
        account = provider.default_account
        assert account is not None


# ── Market data tests ───────────────────────────────────────────────────────


class TestUpstoxProviderMarketData:
    @pytest.mark.asyncio
    async def test_get_quote(
        self, provider: UpstoxProvider, mock_client: MagicMock
    ) -> None:
        from brokers.domain.instrument import Instrument

        inst_key = "NSE_EQ|INE002A01018"
        mock_client.get_quote.return_value = {
            "data": {
                inst_key: {
                    "last_price": "2550.50",
                    "ohlc": {"open": "2540", "high": "2560", "low": "2530", "close": "2545"},
                    "volume": 100000,
                    "net_change": "5.50",
                }
            }
        }

        inst = Instrument(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            provider=provider,  # type: ignore[arg-type]
            security_id=inst_key,
        )
        quote = await provider.get_quote(inst)

        assert quote.symbol == "RELIANCE"
        assert quote.ltp == Decimal("2550.50")
        assert quote.open == Decimal("2540")
        assert quote.high == Decimal("2560")
        assert quote.volume == 100000

    @pytest.mark.asyncio
    async def test_get_quote_raises_on_missing_data(
        self, provider: UpstoxProvider, mock_client: MagicMock
    ) -> None:
        from brokers.domain.instrument import Instrument

        mock_client.get_quote.return_value = {"data": {}}

        inst = Instrument(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            provider=provider,  # type: ignore[arg-type]
            security_id="NSE_EQ|INE002A01018",
        )
        with pytest.raises(ProviderError, match="No quote data"):
            await provider.get_quote(inst)

    @pytest.mark.asyncio
    async def test_get_ltp(
        self, provider: UpstoxProvider, mock_client: MagicMock
    ) -> None:
        from brokers.domain.instrument import Instrument

        inst_key = "NSE_EQ|INE002A01018"
        mock_client.get_ltp.return_value = {
            "data": {
                inst_key: {"last_price": "2550.50"},
            }
        }

        inst = Instrument(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            provider=provider,  # type: ignore[arg-type]
            security_id=inst_key,
        )
        ltp = await provider.get_ltp(inst)
        assert ltp == Decimal("2550.50")

    @pytest.mark.asyncio
    async def test_get_depth(
        self, provider: UpstoxProvider, mock_client: MagicMock
    ) -> None:
        from brokers.domain.instrument import Instrument

        inst_key = "NSE_EQ|INE002A01018"
        mock_client.get_quote.return_value = {
            "data": {
                inst_key: {
                    "last_price": "2550.50",
                    "depth": {
                        "bids": [
                            {"price": "2550.45", "quantity": 100, "orders": 5},
                            {"price": "2550.40", "quantity": 200, "orders": 3},
                        ],
                        "asks": [
                            {"price": "2550.55", "quantity": 150, "orders": 4},
                            {"price": "2550.60", "quantity": 300, "orders": 2},
                        ],
                    },
                }
            }
        }

        inst = Instrument(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            provider=provider,  # type: ignore[arg-type]
            security_id=inst_key,
        )
        depth = await provider.get_depth(inst)

        assert depth.symbol == "RELIANCE"
        assert len(depth.bids) == 2
        assert depth.bids[0].price == Decimal("2550.45")
        assert len(depth.asks) == 2
        assert depth.asks[0].price == Decimal("2550.55")

    @pytest.mark.asyncio
    async def test_get_quote_uses_instruments_dict_for_key(
        self, provider: UpstoxProvider, mock_client: MagicMock
    ) -> None:
        from brokers.domain.instrument import Instrument

        inst_key = "NSE_EQ|INE002A01018"
        mock_client.get_quote.return_value = {
            "data": {
                inst_key: {"last_price": "100", "ohlc": {}},
            }
        }

        inst = Instrument(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            provider=provider,  # type: ignore[arg-type]
            # No security_id — should resolve from instruments dict
        )
        await provider.get_quote(inst)

        # Verify the client was called with the resolved instrument_key
        call_args = mock_client.get_quote.call_args
        assert inst_key in call_args[0][0]


# ── Historical data tests ──────────────────────────────────────────────────


class TestUpstoxProviderHistory:
    @pytest.mark.asyncio
    async def test_get_history(
        self, provider: UpstoxProvider, mock_client: MagicMock
    ) -> None:
        from datetime import date

        from brokers.domain.instrument import Instrument

        mock_client.get_historical_candles.return_value = {
            "data": {
                "candles": [
                    ["2026-07-01T09:15:00+0530", "2540", "2560", "2530", "2550", 100000],
                    ["2026-07-01T09:20:00+0530", "2550", "2570", "2545", "2565", 120000],
                ]
            }
        }

        inst = Instrument(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            provider=provider,  # type: ignore[arg-type]
            security_id="NSE_EQ|INE002A01018",
        )
        series = await provider.get_history(
            inst,
            timeframe="5m",
            from_date=date(2026, 7, 1),
            to_date=date(2026, 7, 2),
        )

        assert series.symbol == "RELIANCE"
        assert series.timeframe == "5m"
        assert len(series.bars) == 2
        assert series.bars[0].open == Decimal("2540")
        assert series.bars[0].close == Decimal("2550")
        assert series.bars[0].volume == 100000

    @pytest.mark.asyncio
    async def test_get_history_empty(
        self, provider: UpstoxProvider, mock_client: MagicMock
    ) -> None:
        from datetime import date

        from brokers.domain.instrument import Instrument

        mock_client.get_historical_candles.return_value = {"data": {"candles": []}}

        inst = Instrument(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            provider=provider,  # type: ignore[arg-type]
            security_id="NSE_EQ|INE002A01018",
        )
        series = await provider.get_history(
            inst,
            timeframe="1d",
            from_date=date(2026, 7, 1),
            to_date=date(2026, 7, 2),
        )

        assert len(series.bars) == 0


# ── Instrument search & resolve tests ──────────────────────────────────────


class TestUpstoxProviderInstruments:
    @pytest.mark.asyncio
    async def test_search_instruments(self, provider: UpstoxProvider) -> None:
        results = await provider.search_instruments("RELI")
        assert len(results) == 1
        assert results[0].symbol == "RELIANCE"
        assert results[0].security_id == "NSE_EQ|INE002A01018"

    @pytest.mark.asyncio
    async def test_search_instruments_no_match(self, provider: UpstoxProvider) -> None:
        results = await provider.search_instruments("NONEXISTENT")
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_get_instruments_all(self, provider: UpstoxProvider) -> None:
        results = await provider.get_instruments()
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_get_instruments_by_exchange(self, provider: UpstoxProvider) -> None:
        results = await provider.get_instruments("NSE")
        assert len(results) == 1

        results = await provider.get_instruments("BSE")
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_resolve_instrument(self, provider: UpstoxProvider) -> None:
        inst = await provider.resolve_instrument("RELIANCE", "NSE")
        assert inst.symbol == "RELIANCE"
        assert inst.exchange == Exchange.NSE
        assert inst.security_id == "NSE_EQ|INE002A01018"

    @pytest.mark.asyncio
    async def test_resolve_instrument_not_in_dict(
        self, provider: UpstoxProvider
    ) -> None:
        inst = await provider.resolve_instrument("TCS", "NSE")
        assert inst.symbol == "TCS"
        # Falls back to generated instrument_key
        assert inst.security_id == "NSE_EQ|TCS"


# ── Execution tests ────────────────────────────────────────────────────────


class TestUpstoxProviderExecution:
    @pytest.mark.asyncio
    async def test_place_order_success(
        self, provider: UpstoxProvider, mock_client: MagicMock
    ) -> None:
        mock_client.place_order.return_value = {
            "data": {"order_id": "upstox_order_001"},
            "status": "success",
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
        assert response.order_id == "upstox_order_001"
        assert response.status == OrderStatus.OPEN
        mock_client.place_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_place_order_http_error(
        self, provider: UpstoxProvider, mock_client: MagicMock
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
        assert response.error_code == "UPSTOX_HTTP_ERROR"

    @pytest.mark.asyncio
    async def test_place_order_generic_error(
        self, provider: UpstoxProvider, mock_client: MagicMock
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
        self, provider: UpstoxProvider, mock_client: MagicMock
    ) -> None:
        mock_client.cancel_order.return_value = {"status": "success"}

        response = await provider.cancel_order("upstox_order_001")

        assert response.success is True
        assert response.order_id == "upstox_order_001"
        assert response.status == OrderStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_order_failure(
        self, provider: UpstoxProvider, mock_client: MagicMock
    ) -> None:
        mock_client.cancel_order.return_value = {
            "status": "failed",
            "message": "Order already executed",
        }

        response = await provider.cancel_order("upstox_order_001")

        assert response.success is False
        assert "Order already executed" in response.message

    @pytest.mark.asyncio
    async def test_cancel_order_http_error(
        self, provider: UpstoxProvider, mock_client: MagicMock
    ) -> None:
        mock_client.cancel_order.side_effect = HttpError("Network error")

        response = await provider.cancel_order("upstox_order_001")

        assert response.success is False
        assert response.error_code == "UPSTOX_HTTP_ERROR"

    @pytest.mark.asyncio
    async def test_modify_order_success(
        self, provider: UpstoxProvider, mock_client: MagicMock
    ) -> None:
        mock_client.modify_order.return_value = {"status": "success"}

        request = ModifyOrderRequest(
            order_id="upstox_order_001",
            quantity=20,
            price=Decimal("2550"),
        )
        response = await provider.modify_order(request)

        assert response.success is True
        assert response.order_id == "upstox_order_001"
        mock_client.modify_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_modify_order_failure(
        self, provider: UpstoxProvider, mock_client: MagicMock
    ) -> None:
        mock_client.modify_order.return_value = {
            "status": "failed",
            "message": "Cannot modify filled order",
        }

        request = ModifyOrderRequest(order_id="upstox_order_001", quantity=20)
        response = await provider.modify_order(request)

        assert response.success is False
        assert "Cannot modify filled order" in response.message

    @pytest.mark.asyncio
    async def test_place_order_uses_resolver_when_instruments_dict_empty(
        self, mock_client: MagicMock
    ) -> None:
        """Verify place_order resolves instrument_key via resolver, not just dict."""
        from brokers.common.instrument_resolver import ResolvedInstrument
        from brokers.domain.instrument import Instrument

        mock_resolver = MagicMock()
        mock_resolver.resolve.return_value = ResolvedInstrument(
            symbol="TCS",
            exchange=Exchange.NSE,
            broker_id="NSE_EQ|INE015A01028",
            segment="NSE_EQ",
        )

        mock_client.place_order.return_value = {
            "data": {"order_id": "upstox_order_002"},
            "status": "success",
        }

        # Provider with NO _instruments dict — only resolver
        p = UpstoxProvider(
            access_token="test_token",
            resolver=mock_resolver,
        )
        p._client = mock_client

        # Instrument without security_id (normal user flow)
        inst = Instrument(
            symbol="TCS",
            exchange=Exchange.NSE,
            provider=p,
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
        # Verify the payload was built with the resolved instrument_key
        call_args = mock_client.place_order.call_args
        payload = call_args[1]["json"] if "json" in call_args[1] else call_args[0][0]
        assert payload["instrument_token"] == "NSE_EQ|INE015A01028"


# ── Portfolio tests ────────────────────────────────────────────────────────


class TestUpstoxProviderPortfolio:
    @pytest.mark.asyncio
    async def test_get_positions(
        self, provider: UpstoxProvider, mock_client: MagicMock
    ) -> None:
        mock_client.get_positions.return_value = {
            "data": [
                {
                    "trading_symbol": "RELIANCE",
                    "segment": "NSE_EQ",
                    "quantity": 10,
                    "average_price": "2500",
                    "last_price": "2550",
                    "unrealized_pnl": "500",
                    "product": "I",
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
        self, provider: UpstoxProvider, mock_client: MagicMock
    ) -> None:
        mock_client.get_positions.return_value = {"data": []}

        positions = await provider.get_positions()
        assert len(positions) == 0

    @pytest.mark.asyncio
    async def test_get_balance(
        self, provider: UpstoxProvider, mock_client: MagicMock
    ) -> None:
        mock_client.get_funds.return_value = {
            "data": {
                "equity": {
                    "available_margin": "100000",
                    "used_margin": "25000",
                    "total_margin": "125000",
                    "start_of_day_margin": "100000",
                    "withdrawable_balance": "75000",
                }
            }
        }

        balance = await provider.get_balance()
        assert balance.available_balance == Decimal("100000")
        assert balance.used_margin == Decimal("25000")
        assert balance.total_value == Decimal("125000")

    @pytest.mark.asyncio
    async def test_get_orders(
        self, provider: UpstoxProvider, mock_client: MagicMock
    ) -> None:
        mock_client.get_orderbook.return_value = {
            "data": [
                {
                    "order_id": "upstox_001",
                    "trading_symbol": "RELIANCE",
                    "segment": "NSE_EQ",
                    "transaction_type": "BUY",
                    "quantity": 10,
                    "order_type": "MARKET",
                    "product": "I",
                    "status": "complete",
                    "filled_quantity": 10,
                    "average_price": "2550",
                }
            ]
        }

        orders = await provider.get_orders()
        assert len(orders) == 1

    @pytest.mark.asyncio
    async def test_get_trades(
        self, provider: UpstoxProvider, mock_client: MagicMock
    ) -> None:
        mock_client.get_trades.return_value = {
            "data": [
                {
                    "trade_id": "trade_001",
                    "order_id": "upstox_001",
                    "trading_symbol": "RELIANCE",
                    "segment": "NSE_EQ",
                    "transaction_type": "BUY",
                    "quantity": 10,
                    "average_price": "2550",
                    "product": "I",
                }
            ]
        }

        trades = await provider.get_trades()
        assert len(trades) == 1
        assert trades[0].trade_id == "trade_001"
        assert trades[0].price == Decimal("2550")

    @pytest.mark.asyncio
    async def test_get_holdings(
        self, provider: UpstoxProvider, mock_client: MagicMock
    ) -> None:
        mock_client.get_holdings.return_value = {
            "data": [
                {
                    "trading_symbol": "RELIANCE",
                    "segment": "NSE_EQ",
                    "quantity": 100,
                    "average_price": "2000",
                    "last_price": "2550",
                }
            ]
        }

        holdings = await provider.get_holdings()
        assert len(holdings) == 1
        assert holdings[0].symbol == "RELIANCE"
        assert holdings[0].quantity == 100
        assert holdings[0].average_price == Decimal("2000")


# ── Streaming tests ────────────────────────────────────────────────────────


class TestUpstoxProviderStreaming:
    @pytest.mark.asyncio
    async def test_subscribe_quotes_returns_subscription(
        self, provider: UpstoxProvider
    ) -> None:
        from brokers.domain.instrument import Instrument
        from brokers.domain.values import Subscription

        inst = Instrument(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            provider=provider,  # type: ignore[arg-type]
            security_id="NSE_EQ|INE002A01018",
        )
        sub = await provider.subscribe_quotes([inst])
        assert isinstance(sub, Subscription)
        assert sub.is_active

    @pytest.mark.asyncio
    async def test_subscribe_depth_returns_subscription(
        self, provider: UpstoxProvider
    ) -> None:
        from brokers.domain.instrument import Instrument
        from brokers.domain.values import Subscription

        inst = Instrument(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            provider=provider,  # type: ignore[arg-type]
            security_id="NSE_EQ|INE002A01018",
        )
        sub = await provider.subscribe_depth([inst])
        assert isinstance(sub, Subscription)

    @pytest.mark.asyncio
    async def test_subscribe_orders_returns_subscription(
        self, provider: UpstoxProvider
    ) -> None:
        from brokers.domain.values import Subscription

        sub = await provider.subscribe_orders()
        assert isinstance(sub, Subscription)


# ── Resolver wiring tests ──────────────────────────────────────────────────


class TestUpstoxProviderResolver:
    @pytest.mark.asyncio
    async def test_resolve_instrument_with_resolver(self) -> None:
        from brokers.common.instrument_resolver import ResolvedInstrument

        mock_resolver = MagicMock()
        mock_resolver.resolve.return_value = ResolvedInstrument(
            symbol="TCS",
            exchange=Exchange.NSE,
            broker_id="NSE_EQ|INE123A01018",
            segment="NSE_EQ",
            lot_size=1,
            tick_size=Decimal("0.05"),
            trading_symbol="TCS",
        )

        p = UpstoxProvider(access_token="tok", resolver=mock_resolver)
        inst = await p.resolve_instrument("TCS", "NSE")

        assert inst.security_id == "NSE_EQ|INE123A01018"
        assert inst.lot_size == 1
        assert inst.trading_symbol == "TCS"
        mock_resolver.resolve.assert_called_once()

    @pytest.mark.asyncio
    async def test_resolve_instrument_resolver_not_found(self) -> None:
        from brokers.common.instrument_resolver import InstrumentNotFoundError

        mock_resolver = MagicMock()
        mock_resolver.resolve.side_effect = InstrumentNotFoundError("UNKNOWN", "NSE", "upstox")

        p = UpstoxProvider(access_token="tok", resolver=mock_resolver)
        inst = await p.resolve_instrument("UNKNOWN", "NSE")

        # Falls back gracefully
        assert inst.symbol == "UNKNOWN"
        assert inst.security_id != ""

    @pytest.mark.asyncio
    async def test_search_instruments_with_resolver(self) -> None:
        from brokers.common.instrument_resolver import ResolvedInstrument

        mock_resolver = MagicMock()
        mock_resolver.search.return_value = [
            ResolvedInstrument(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                broker_id="NSE_EQ|INE002A01018",
                segment="NSE_EQ",
                lot_size=1,
                trading_symbol="RELIANCE",
            ),
        ]

        p = UpstoxProvider(access_token="tok", resolver=mock_resolver)
        results = await p.search_instruments("RELI")

        assert len(results) == 1
        assert results[0].symbol == "RELIANCE"
        assert results[0].security_id == "NSE_EQ|INE002A01018"
        mock_resolver.search.assert_called_once_with("RELI", limit=20)

    @pytest.mark.asyncio
    async def test_get_quote_uses_resolver_for_instrument_key(self) -> None:
        from brokers.common.instrument_resolver import ResolvedInstrument
        from brokers.domain.instrument import Instrument

        mock_resolver = MagicMock()
        mock_resolver.resolve.return_value = ResolvedInstrument(
            symbol="TCS",
            exchange=Exchange.NSE,
            broker_id="NSE_EQ|INE123A01018",
            segment="NSE_EQ",
        )

        mock_client = MagicMock()
        mock_client.get_quote.return_value = {
            "data": {
                "NSE_EQ|INE123A01018": {"last_price": "3500", "ohlc": {}},
            }
        }

        p = UpstoxProvider(access_token="tok", resolver=mock_resolver)
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
