"""Integration-style tests using mocked provider (no live broker)."""

import time
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from tradex.broker.auth import TokenInfo
from tradex.broker.provider import (
    AuthProvider,
    BrokerProvider,
    ExecutionProvider,
    MarketDataProvider,
    PortfolioProvider,
    StreamingProvider,
)
from tradex.core.di import Container
from tradex.core.errors import BrokerError
from tradex.core.events import DomainEvent, EventBus
from tradex.core.metrics import MetricsCollector
from tradex.core.storage import SessionSnapshot, TokenStore
from tradex.domain.enums import (
    Exchange,
    ExchangeSegment,
    InstrumentType,
    OrderStatus,
    OrderType,
    ProductType,
    Side,
)
from tradex.domain.execution import Order, Trade
from tradex.domain.instruments import Instrument
from tradex.domain.market_data import OHLCV, Quote

# ---------------------------------------------------------------------------
# Helpers: build canned domain objects
# ---------------------------------------------------------------------------


def _make_quote() -> Quote:
    return Quote(
        security_id="13",
        trading_symbol="NIFTY",
        exchange_segment="IDX_I",
        last_price=Decimal("22500"),
        open=Decimal("22400"),
        high=Decimal("22600"),
        low=Decimal("22300"),
        close=Decimal("22450"),
        volume=5000000,
        bid_price=Decimal("22499"),
        ask_price=Decimal("22501"),
        bid_quantity=100,
        ask_quantity=100,
    )


def _make_order() -> Order:
    return Order(
        order_id="ORD_001",
        security_id="13",
        trading_symbol="NIFTY",
        exchange_segment="IDX_I",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        product_type=ProductType.MARGIN,
        quantity=50,
        price=Decimal("22500"),
        status=OrderStatus.PLACED,
        filled_quantity=50,
        pending_quantity=0,
        average_price=Decimal("22500"),
    )


def _make_instrument() -> Instrument:
    return Instrument(
        security_id="13",
        trading_symbol="NIFTY",
        display_symbol="NIFTY 50",
        exchange=Exchange.INDEX,
        exchange_segment=ExchangeSegment.INDEX,
        instrument_type=InstrumentType.INDEX,
        lot_size=50,
    )


def _make_trade() -> Trade:
    return Trade(
        trade_id="TRD_001",
        order_id="ORD_001",
        security_id="13",
        trading_symbol="NIFTY",
        side=Side.BUY,
        quantity=50,
        price=Decimal("22500"),
    )


# ---------------------------------------------------------------------------
# Mock sub-providers
# ---------------------------------------------------------------------------


class MockAuthProvider(AuthProvider):
    def __init__(self):
        self._authenticated = False
        self._token = None

    async def connect(self) -> None:
        self._token = TokenInfo(
            access_token="mock_at",
            refresh_token="mock_rt",
            expires_at=time.time() + 3600,
            issued_at=time.time(),
        )
        self._authenticated = True

    async def disconnect(self) -> None:
        self._authenticated = False
        self._token = None

    async def refresh_token(self) -> TokenInfo:
        self._token = TokenInfo(
            access_token="refreshed_at",
            refresh_token="refreshed_rt",
            expires_at=time.time() + 3600,
            issued_at=time.time(),
        )
        return self._token

    async def is_authenticated(self) -> bool:
        return self._authenticated

    async def get_profile(self):
        return {}


class MockExecutionProvider(ExecutionProvider):
    def __init__(self):
        self._orders: list[Order] = []

    async def place_order(self, **kwargs) -> Order:
        order = _make_order()
        self._orders.append(order)
        return order

    async def modify_order(self, **kwargs) -> Order:
        order = _make_order()
        order.order_id = kwargs.get("order_id", "MODIFIED")
        order.status = OrderStatus.ACCEPTED
        return order

    async def cancel_order(self, order_id: str) -> None:
        pass

    async def get_order(self, order_id: str) -> Order:
        return _make_order()

    async def get_orders(self) -> list[Order]:
        return self._orders

    async def get_trades(self, order_id=None) -> list[Trade]:
        return [_make_trade()]

    async def get_trade_history(self, start_date, end_date, page=0) -> list[Trade]:
        return [_make_trade()]


class MockMarketDataProvider(MarketDataProvider):
    async def get_quote(self, security_id: str, exchange: str) -> Quote:
        return _make_quote()

    async def get_quotes(self, securities) -> dict:
        return {}

    async def get_ohlcv(self, **kwargs) -> list[OHLCV]:
        return []

    async def get_minute_data(self, **kwargs) -> list[OHLCV]:
        return []

    async def get_option_chain(self, **kwargs):
        return None

    async def get_expiry_list(self, **kwargs) -> list[str]:
        return []

    async def get_depth(self, **kwargs):
        return None


class MockPortfolioProvider(PortfolioProvider):
    async def get_holdings(self):
        return []

    async def get_positions(self):
        return []

    async def get_fund_limits(self):
        return MagicMock()

    async def calculate_margin(self, **kwargs):
        return {"sufficient": True, "total_margin": 0, "available_balance": 0}


class MockStreamingProvider(StreamingProvider):
    def __init__(self):
        self._connected = False

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    async def subscribe(self, instruments) -> None:
        pass

    async def unsubscribe(self, instruments) -> None:
        pass

    async def ticks(self):
        return
        yield  # make it an async generator

    @property
    def is_connected(self) -> bool:
        return self._connected


class MockInstrumentMapper:
    async def resolve(self, symbol: str, exchange=None) -> Instrument:
        return _make_instrument()


class MockBrokerProvider(BrokerProvider):
    def __init__(self):
        self._auth = MockAuthProvider()
        self._execution = MockExecutionProvider()
        self._market_data = MockMarketDataProvider()
        self._portfolio = MockPortfolioProvider()
        self._streaming = MockStreamingProvider()
        self._mapper = MockInstrumentMapper()
        self._connected = False

    @property
    def name(self) -> str:
        return "mock"

    async def connect(self) -> None:
        await self._auth.connect()
        self._connected = True

    async def disconnect(self) -> None:
        await self._auth.disconnect()
        await self._streaming.disconnect()
        self._connected = False

    async def health(self):
        return MagicMock(is_healthy=True)

    @property
    def auth(self) -> AuthProvider:
        return self._auth

    @property
    def execution(self) -> ExecutionProvider:
        return self._execution

    @property
    def market_data(self) -> MarketDataProvider:
        return self._market_data

    @property
    def portfolio(self) -> PortfolioProvider:
        return self._portfolio

    @property
    def streaming(self) -> StreamingProvider:
        return self._streaming

    @property
    def mapper(self):
        return self._mapper

    async def get_capabilities(self) -> list[str]:
        return ["basic_orders", "quotes"]


# ---------------------------------------------------------------------------
# Test: Full workflow with mocked provider
# ---------------------------------------------------------------------------


class TestFullWorkflow:
    @pytest.mark.asyncio
    async def test_connect_resolve_get_quote_place_order_get_orders_disconnect(self):
        broker = MockBrokerProvider()
        bus = EventBus()
        metrics = MetricsCollector()
        events_received: list[DomainEvent] = []

        @bus.on(DomainEvent)
        async def track_events(event):
            events_received.append(event)

        # Step 1: connect
        await broker.connect()
        assert await broker.auth.is_authenticated()

        # Step 2: resolve instrument
        instrument = await broker.mapper.resolve("NIFTY")
        assert instrument.security_id == "13"
        assert instrument.trading_symbol == "NIFTY"
        metrics.increment("instruments_resolved")

        # Step 3: get quote
        quote = await broker.market_data.get_quote(
            instrument.security_id, str(instrument.exchange_segment)
        )
        assert quote.last_price == Decimal("22500")
        metrics.increment("quotes_fetched")

        # Step 4: place order
        order = await broker.execution.place_order(
            security_id=instrument.security_id,
            exchange_segment=str(instrument.exchange_segment),
            side=Side.BUY,
            quantity=50,
            order_type=OrderType.LIMIT,
            product_type=ProductType.MARGIN,
            price=22500.0,
        )
        assert order.order_id == "ORD_001"
        assert order.status == OrderStatus.PLACED
        metrics.increment("orders_placed")
        await bus.publish(DomainEvent(source="order_placed"))

        # Step 5: get orders
        orders = await broker.execution.get_orders()
        assert len(orders) == 1
        assert orders[0].order_id == "ORD_001"
        metrics.increment("orders_fetched")

        # Step 6: disconnect
        await broker.disconnect()
        assert await broker.auth.is_authenticated() is False

        # Verify metrics
        assert metrics.get_counter("instruments_resolved") == 1
        assert metrics.get_counter("quotes_fetched") == 1
        assert metrics.get_counter("orders_placed") == 1
        assert metrics.get_counter("orders_fetched") == 1

        # Verify event bus received events
        assert len(events_received) >= 1

    @pytest.mark.asyncio
    async def test_get_trades_after_order(self):
        broker = MockBrokerProvider()
        await broker.connect()

        order = await broker.execution.place_order(
            security_id="13",
            exchange_segment="IDX_I",
            side=Side.BUY,
            quantity=50,
            order_type=OrderType.LIMIT,
            product_type=ProductType.MARGIN,
            price=22500.0,
        )

        trades = await broker.execution.get_trades(order.order_id)
        assert len(trades) == 1
        assert trades[0].trade_id == "TRD_001"

    @pytest.mark.asyncio
    async def test_capabilities(self):
        broker = MockBrokerProvider()
        caps = await broker.get_capabilities()
        assert "basic_orders" in caps
        assert "quotes" in caps


# ---------------------------------------------------------------------------
# Test: Error recovery flow (fail first, succeed on retry)
# ---------------------------------------------------------------------------


class TestErrorRecovery:
    @pytest.mark.asyncio
    async def test_retry_on_intermittent_failure(self):
        """Provider fails on first call, succeeds on second."""
        call_count = 0

        class FlakyProvider(MarketDataProvider):
            async def get_quote(self, security_id, exchange):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise BrokerError("Temporary failure", code="DH-909")
                return _make_quote()

            async def get_quotes(self, securities):
                return {}

            async def get_ohlcv(self, **kwargs):
                return []

            async def get_minute_data(self, **kwargs):
                return []

            async def get_option_chain(self, **kwargs):
                return None

            async def get_expiry_list(self, **kwargs):
                return []

            async def get_depth(self, **kwargs):
                return None

        provider = FlakyProvider()
        max_retries = 3
        result = None

        for attempt in range(max_retries):
            try:
                result = await provider.get_quote("13", "IDX_I")
                break
            except BrokerError:
                if attempt == max_retries - 1:
                    raise

        assert result is not None
        assert result.last_price == Decimal("22500")
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_permanent_failure_raises_after_retries(self):
        """Provider always fails — exception propagates."""

        class AlwaysFailProvider(MarketDataProvider):
            async def get_quote(self, security_id, exchange):
                raise BrokerError("Permanent failure", code="DH-908")

            async def get_quotes(self, securities):
                return {}

            async def get_ohlcv(self, **kwargs):
                return []

            async def get_minute_data(self, **kwargs):
                return []

            async def get_option_chain(self, **kwargs):
                return None

            async def get_expiry_list(self, **kwargs):
                return []

            async def get_depth(self, **kwargs):
                return None

        provider = AlwaysFailProvider()
        with pytest.raises(BrokerError):
            await provider.get_quote("13", "IDX_I")


# ---------------------------------------------------------------------------
# Test: Session persistence flow
# ---------------------------------------------------------------------------


class TestSessionPersistence:
    @pytest.mark.asyncio
    async def test_save_and_load_session(self, tmp_path):
        store = TokenStore(storage_dir=str(tmp_path))
        token = TokenInfo(
            access_token="persist_at",
            refresh_token="persist_rt",
            expires_at=time.time() + 7200,
            issued_at=time.time(),
        )
        snapshot = SessionSnapshot.from_token_info(
            broker="mock_broker",
            client_id="test_client",
            token=token,
        )

        await store.save(snapshot)
        loaded = await store.load("mock_broker", "test_client")

        assert loaded is not None
        restored_token = loaded.to_token_info()
        assert restored_token.access_token == "persist_at"
        assert restored_token.refresh_token == "persist_rt"

        # Verify validity
        assert store.is_valid(loaded) is True

    @pytest.mark.asyncio
    async def test_session_expiry_detected(self, tmp_path):
        store = TokenStore(storage_dir=str(tmp_path))
        token = TokenInfo(
            access_token="expired_at",
            refresh_token="expired_rt",
            expires_at=time.time() - 100,  # already expired
            issued_at=time.time() - 7200,
        )
        snapshot = SessionSnapshot.from_token_info(
            broker="mock_broker",
            client_id="test_client",
            token=token,
        )
        await store.save(snapshot)
        loaded = await store.load("mock_broker", "test_client")

        assert loaded is not None
        assert store.is_valid(loaded) is False

    @pytest.mark.asyncio
    async def test_delete_and_reload(self, tmp_path):
        store = TokenStore(storage_dir=str(tmp_path))
        snapshot = SessionSnapshot(broker="b", client_id="c", access_token="t")
        await store.save(snapshot)
        assert await store.load("b", "c") is not None
        await store.delete("b", "c")
        assert await store.load("b", "c") is None


# ---------------------------------------------------------------------------
# Test: DI Container wiring
# ---------------------------------------------------------------------------


class TestDIWiring:
    def test_wire_full_platform(self):
        container = Container()
        container.register_instance(EventBus())
        container.register_instance(MetricsCollector())

        bus = container.resolve(EventBus)
        metrics = container.resolve(MetricsCollector)

        # Both should resolve to singletons
        assert container.resolve(EventBus) is bus
        assert container.resolve(MetricsCollector) is metrics

    def test_factory_produces_new_instances(self):
        container = Container()
        container.register_factory(lambda: EventBus(), EventBus)
        bus1 = container.resolve(EventBus)
        bus2 = container.resolve(EventBus)
        # After first resolve, factory result is cached as singleton
        assert bus1 is bus2

    def test_child_container_inheritance(self):
        parent = Container()
        parent.register_instance(MetricsCollector())

        child = parent.create_child()
        # Child should resolve parent's registrations
        metrics = child.resolve(MetricsCollector)
        assert isinstance(metrics, MetricsCollector)
