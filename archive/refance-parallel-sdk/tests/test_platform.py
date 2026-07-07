"""Tests for the BrokerPlatform public API using a mock provider."""

from decimal import Decimal

import pytest
from tradex.broker.capability import BrokerCapability, CapabilityNames, CapabilityRegistry
from tradex.broker.extensions import ExtensionRegistry
from tradex.broker.provider import (
    AuthProvider,
    BrokerProvider,
    ExecutionProvider,
    MarketDataProvider,
    PortfolioProvider,
    StreamingProvider,
)
from tradex.core.events import DomainEvent
from tradex.core.health import HealthReport, HealthStatus
from tradex.domain.account import FundLimits
from tradex.domain.enums import (
    Exchange,
    ExchangeSegment,
    InstrumentType,
    OrderStatus,
    OrderType,
    ProductType,
    Side,
    Validity,
)
from tradex.domain.execution import Order, Trade
from tradex.domain.instruments import Instrument
from tradex.domain.mapping import InstrumentMapper, SecurityMapping
from tradex.domain.market_data import MarketDepth, OptionChain, Quote
from tradex.domain.portfolio import Holding, Position
from tradex.platform import BrokerPlatform

# ============================================================
# Mock Providers
# ============================================================


class MockAuthProvider(AuthProvider):
    def __init__(self):
        self._connected = False

    async def connect(self):
        self._connected = True

    async def disconnect(self):
        self._connected = False

    async def refresh_token(self):
        pass

    async def is_authenticated(self):
        return self._connected

    async def get_profile(self):
        from tradex.domain.account import AccountProfile

        return AccountProfile(client_id="mock_123", active_segments=["NSE_EQ"])


class MockExecutionProvider(ExecutionProvider):
    def __init__(self):
        self._orders: dict[str, Order] = {}
        self._trades: list[Trade] = []

    async def place_order(
        self,
        security_id,
        exchange_segment,
        side,
        quantity,
        order_type,
        product_type,
        price,
        trigger_price=0,
        disclosed_quantity=0,
        after_market_order=False,
        validity=Validity.DAY,
        tag="",
    ):
        order = Order(
            order_id="MOCK_001",
            correlation_id=tag,
            security_id=security_id,
            exchange_segment=exchange_segment,
            side=side,
            order_type=order_type,
            product_type=product_type,
            quantity=quantity,
            price=Decimal(str(price)),
            tag=tag,
            status=OrderStatus.PLACED,
        )
        self._orders[order.order_id] = order
        return order

    async def modify_order(
        self,
        order_id,
        order_type,
        quantity,
        price,
        trigger_price=0,
        disclosed_quantity=0,
        validity=Validity.DAY,
    ):
        order = self._orders.get(order_id)
        if order:
            order.quantity = quantity
            order.price = Decimal(str(price))
        return order or Order(order_id=order_id)

    async def cancel_order(self, order_id):
        if order_id in self._orders:
            self._orders[order_id].status = OrderStatus.CANCELLED

    async def get_order(self, order_id):
        return self._orders.get(order_id, Order(order_id=order_id))

    async def get_orders(self):
        return list(self._orders.values())

    async def get_trades(self, order_id=None):
        trades = self._trades
        if order_id:
            trades = [t for t in trades if t.order_id == order_id]
        return trades

    async def get_trade_history(self, start_date, end_date, page=0):
        return self._trades


class MockMarketDataProvider(MarketDataProvider):
    async def get_quote(self, security_id, exchange):
        return Quote(
            security_id=security_id,
            exchange=exchange,
            last_price=Decimal("2450.50"),
            close=Decimal("2440"),
        )

    async def get_quotes(self, securities):
        result = {}
        for exchange, ids in securities.items():
            result[exchange] = {}
            for sid in ids:
                result[exchange][sid] = Quote(
                    security_id=sid,
                    exchange=exchange,
                    last_price=Decimal("2450"),
                )
        return result

    async def get_ohlcv(
        self,
        security_id,
        exchange,
        instrument_type,
        start_date,
        end_date,
        expiry_code=0,
        include_oi=False,
    ):
        return []

    async def get_minute_data(
        self,
        security_id,
        exchange,
        instrument_type,
        start_date,
        end_date,
        interval=1,
        include_oi=False,
    ):
        return []

    async def get_option_chain(self, underlying_security_id, exchange, expiry):
        return OptionChain(
            spot_price=Decimal("24500"),
            expiry=expiry,
            strikes=[],
        )

    async def get_expiry_list(self, underlying_security_id, exchange):
        return ["2025-03-27", "2025-04-03"]

    async def get_depth(self, security_id, exchange):
        return MarketDepth(security_id=security_id, exchange=exchange, levels=[])


class MockPortfolioProvider(PortfolioProvider):
    async def get_holdings(self):
        return [
            Holding(security_id="2885", trading_symbol="RELIANCE", total_quantity=10),
        ]

    async def get_positions(self):
        return [
            Position(security_id="49081", net_quantity=75, realized_profit=Decimal("500")),
        ]

    async def get_fund_limits(self):
        return FundLimits(available_balance=Decimal("100000"))

    async def calculate_margin(
        self,
        security_id,
        exchange,
        side,
        quantity,
        product_type,
        price,
        trigger_price=0,
    ):
        return {"total_margin": 50000, "sufficient": True}


class MockStreamingProvider(StreamingProvider):
    def __init__(self):
        self._connected = False

    async def connect(self):
        self._connected = True

    async def disconnect(self):
        self._connected = False

    async def subscribe(self, instruments):
        pass

    async def unsubscribe(self, instruments):
        pass

    async def ticks(self):
        yield {}

    @property
    def is_connected(self):
        return self._connected


class MockInstrumentMapper(InstrumentMapper):
    def __init__(self):
        super().__init__("mock")

    async def load(self, rows):
        # Add some mock mappings
        for row in rows:
            mapping = SecurityMapping(
                canonical_symbol=row.get("symbol", ""),
                canonical_exchange=Exchange.NSE,
                broker_security_id=row.get("security_id", ""),
                instrument_type=InstrumentType.EQUITY,
            )
            key = f"{mapping.canonical_symbol}:{mapping.canonical_exchange.value}"
            await self._cache.put(key, mapping)
            broker_key = f"{mapping.broker_security_id}:{self._broker}"
            await self._reverse_cache.put(broker_key, mapping)
            self._mappings[broker_key] = mapping
        self._loaded = True


class MockBrokerProvider(BrokerProvider):
    def __init__(self):
        self._auth = MockAuthProvider()
        self._execution = MockExecutionProvider()
        self._market_data = MockMarketDataProvider()
        self._portfolio = MockPortfolioProvider()
        self._streaming = MockStreamingProvider()
        self._mapper = MockInstrumentMapper()
        self._capabilities = CapabilityRegistry()
        self._capabilities.register_many(
            [
                BrokerCapability(name=CapabilityNames.SUPER_ORDERS, description="Super orders"),
                BrokerCapability(name=CapabilityNames.DEPTH_20, description="20-level depth"),
            ]
        )
        self._extensions = ExtensionRegistry(self._capabilities)
        self._health = HealthReport()

    @property
    def name(self):
        return "mock"

    async def connect(self):
        await self._auth.connect()

    async def disconnect(self):
        await self._auth.disconnect()
        await self._streaming.disconnect()

    async def health(self):
        report = HealthReport()
        report.add_component(
            __import__("tradex.core.health", fromlist=["ComponentHealth"]).ComponentHealth(
                name="auth",
                status=HealthStatus.HEALTHY
                if await self._auth.is_authenticated()
                else HealthStatus.UNHEALTHY,
            )
        )
        return report

    @property
    def auth(self):
        return self._auth

    @property
    def execution(self):
        return self._execution

    @property
    def market_data(self):
        return self._market_data

    @property
    def portfolio(self):
        return self._portfolio

    @property
    def streaming(self):
        return self._streaming

    @property
    def mapper(self):
        return self._mapper

    @property
    def capabilities(self):
        return self._capabilities

    @property
    def extensions(self):
        return self._extensions

    async def get_capabilities(self):
        return self._capabilities.names


# ============================================================
# BrokerPlatform Tests
# ============================================================


class TestBrokerPlatform:
    def _make_platform(self):
        provider = MockBrokerProvider()
        return BrokerPlatform(provider, log_level="CRITICAL")

    @pytest.mark.asyncio
    async def test_connect_disconnect(self):
        platform = self._make_platform()
        assert not platform.is_connected

        await platform.connect()
        assert platform.is_connected

        await platform.disconnect()
        assert not platform.is_connected

    @pytest.mark.asyncio
    async def test_provider_name(self):
        platform = self._make_platform()
        assert platform.provider_name == "mock"

    @pytest.mark.asyncio
    async def test_health(self):
        platform = self._make_platform()
        await platform.connect()
        report = await platform.health()
        assert isinstance(report, HealthReport)

    @pytest.mark.asyncio
    async def test_place_order(self):
        platform = self._make_platform()
        await platform.connect()

        instrument = Instrument(
            security_id="2885",
            trading_symbol="RELIANCE",
            exchange_segment=ExchangeSegment.NSE_EQ,
        )
        order = await platform.place_order(
            instrument=instrument,
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            product_type=ProductType.CNC,
            quantity=10,
            price=2450.0,
            tag="test",
        )
        assert isinstance(order, Order)
        assert order.order_id == "MOCK_001"
        assert order.security_id == "2885"
        assert order.side == Side.BUY

    @pytest.mark.asyncio
    async def test_modify_order(self):
        platform = self._make_platform()
        await platform.connect()

        # Place first
        instrument = Instrument(
            security_id="2885",
            exchange_segment=ExchangeSegment.NSE_EQ,
        )
        order = await platform.place_order(
            instrument=instrument,
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            product_type=ProductType.CNC,
            quantity=10,
            price=2450.0,
        )

        modified = await platform.modify_order(
            order_id=order.order_id,
            order_type=OrderType.LIMIT,
            quantity=20,
            price=2460.0,
        )
        assert modified.quantity == 20

    @pytest.mark.asyncio
    async def test_cancel_order(self):
        platform = self._make_platform()
        await platform.connect()

        instrument = Instrument(
            security_id="2885",
            exchange_segment=ExchangeSegment.NSE_EQ,
        )
        order = await platform.place_order(
            instrument=instrument,
            side=Side.BUY,
            order_type=OrderType.MARKET,
            product_type=ProductType.INTRADAY,
            quantity=10,
            price=0,
        )
        await platform.cancel_order(order.order_id)
        # No exception = success

    @pytest.mark.asyncio
    async def test_get_order(self):
        platform = self._make_platform()
        await platform.connect()

        instrument = Instrument(
            security_id="2885",
            exchange_segment=ExchangeSegment.NSE_EQ,
        )
        order = await platform.place_order(
            instrument=instrument,
            side=Side.BUY,
            order_type=OrderType.MARKET,
            product_type=ProductType.INTRADAY,
            quantity=10,
            price=0,
        )
        fetched = await platform.get_order(order.order_id)
        assert fetched.order_id == order.order_id

    @pytest.mark.asyncio
    async def test_get_orders(self):
        platform = self._make_platform()
        await platform.connect()

        orders = await platform.get_orders()
        assert isinstance(orders, list)

    @pytest.mark.asyncio
    async def test_get_trades(self):
        platform = self._make_platform()
        await platform.connect()

        trades = await platform.get_trades()
        assert isinstance(trades, list)

    @pytest.mark.asyncio
    async def test_get_quote(self):
        platform = self._make_platform()
        await platform.connect()

        instrument = Instrument(
            security_id="2885",
            exchange_segment=ExchangeSegment.NSE_EQ,
        )
        quote = await platform.get_quote(instrument)
        assert isinstance(quote, Quote)
        assert quote.security_id == "2885"

    @pytest.mark.asyncio
    async def test_get_quotes(self):
        platform = self._make_platform()
        await platform.connect()

        instruments = [
            Instrument(security_id="2885", exchange_segment=ExchangeSegment.NSE_EQ),
            Instrument(security_id="1153", exchange_segment=ExchangeSegment.NSE_EQ),
        ]
        quotes = await platform.get_quotes(instruments)
        assert isinstance(quotes, dict)
        assert "NSE_EQ" in quotes

    @pytest.mark.asyncio
    async def test_get_history(self):
        platform = self._make_platform()
        await platform.connect()

        instrument = Instrument(
            security_id="2885",
            exchange_segment=ExchangeSegment.NSE_EQ,
            instrument_type=InstrumentType.EQUITY,
        )
        history = await platform.get_history(
            instrument=instrument,
            start_date="2024-01-01",
            end_date="2024-01-31",
        )
        assert isinstance(history, list)

    @pytest.mark.asyncio
    async def test_get_option_chain(self):
        platform = self._make_platform()
        await platform.connect()

        instrument = Instrument(
            security_id="13",
            exchange_segment=ExchangeSegment.INDEX,
        )
        chain = await platform.get_option_chain(
            underlying=instrument,
            expiry="2025-03-27",
        )
        assert isinstance(chain, OptionChain)
        assert chain.expiry == "2025-03-27"

    @pytest.mark.asyncio
    async def test_get_expiry_list(self):
        platform = self._make_platform()
        await platform.connect()

        instrument = Instrument(
            security_id="13",
            exchange_segment=ExchangeSegment.INDEX,
        )
        expiry_list = await platform.get_expiry_list(instrument)
        assert isinstance(expiry_list, list)
        assert len(expiry_list) == 2

    @pytest.mark.asyncio
    async def test_get_holdings(self):
        platform = self._make_platform()
        await platform.connect()

        holdings = await platform.get_holdings()
        assert len(holdings) == 1
        assert holdings[0].security_id == "2885"

    @pytest.mark.asyncio
    async def test_get_positions(self):
        platform = self._make_platform()
        await platform.connect()

        positions = await platform.get_positions()
        assert len(positions) == 1
        assert positions[0].net_quantity == 75

    @pytest.mark.asyncio
    async def test_get_fund_limits(self):
        platform = self._make_platform()
        await platform.connect()

        fl = await platform.get_fund_limits()
        assert fl.available_balance == Decimal("100000")

    @pytest.mark.asyncio
    async def test_calculate_margin(self):
        platform = self._make_platform()
        await platform.connect()

        instrument = Instrument(
            security_id="49081",
            exchange_segment=ExchangeSegment.NSE_FNO,
        )
        margin = await platform.calculate_margin(
            instrument=instrument,
            side=Side.BUY,
            quantity=75,
            product_type=ProductType.MARGIN,
            price=24500,
        )
        assert margin["total_margin"] == 50000
        assert margin["sufficient"] is True

    @pytest.mark.asyncio
    async def test_capabilities(self):
        platform = self._make_platform()
        caps = platform.capabilities
        assert CapabilityNames.SUPER_ORDERS in caps
        assert CapabilityNames.DEPTH_20 in caps

    @pytest.mark.asyncio
    async def test_has_capability(self):
        platform = self._make_platform()
        assert platform.has_capability(CapabilityNames.SUPER_ORDERS)
        assert not platform.has_capability("nonexistent")

    @pytest.mark.asyncio
    async def test_event_subscription(self):
        platform = self._make_platform()
        received = []

        @platform.on(DomainEvent)
        async def handler(event):
            received.append(event)

        event = DomainEvent(source="test")
        await platform.publish_event(event)
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_subscribe_event(self):
        platform = self._make_platform()
        received = []

        async def handler(event):
            received.append(event)

        platform.subscribe_event(DomainEvent, handler)
        event = DomainEvent(source="test")
        await platform.publish_event(event)
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_get_depth(self):
        platform = self._make_platform()
        await platform.connect()

        instrument = Instrument(
            security_id="2885",
            exchange_segment=ExchangeSegment.NSE_EQ,
        )
        depth = await platform.get_depth(instrument)
        assert isinstance(depth, MarketDepth)

    @pytest.mark.asyncio
    async def test_get_minute_history(self):
        platform = self._make_platform()
        await platform.connect()

        instrument = Instrument(
            security_id="2885",
            exchange_segment=ExchangeSegment.NSE_EQ,
            instrument_type=InstrumentType.EQUITY,
        )
        bars = await platform.get_minute_history(
            instrument=instrument,
            start_date="2024-01-01",
            end_date="2024-01-01",
            interval=5,
        )
        assert isinstance(bars, list)

    @pytest.mark.asyncio
    async def test_resolve_instrument(self):
        platform = self._make_platform()
        await platform.connect()

        # Load some mock data into mapper
        await platform._provider.mapper.load(
            [
                {"symbol": "RELIANCE", "security_id": "2885"},
            ]
        )

        instrument = await platform.resolve_instrument("RELIANCE", Exchange.NSE)
        assert instrument is not None
        assert instrument.security_id == "2885"

    @pytest.mark.asyncio
    async def test_search_instruments(self):
        platform = self._make_platform()
        await platform.connect()

        await platform._provider.mapper.load(
            [
                {"symbol": "RELIANCE", "security_id": "2885"},
                {"symbol": "RELIANCE", "security_id": "2886"},
            ]
        )

        results = await platform.search_instruments("RELIANCE", Exchange.NSE)
        assert len(results) == 2
