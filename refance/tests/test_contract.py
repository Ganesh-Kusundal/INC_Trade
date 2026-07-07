"""Contract tests — verify the SPI (Service Provider Interface) contracts.

Ensures that any broker provider implementation conforms to the abstract
interfaces defined in broker/provider.py. These tests validate the ABC
structure and that a mock implementation satisfies the contract.
"""

import asyncio
from abc import ABC

import pytest
from tradex.broker.capability import BrokerCapability, CapabilityRegistry
from tradex.broker.extensions import BrokerExtension, ExtensionRegistry
from tradex.broker.provider import (
    AuthProvider,
    BrokerProvider,
    ExecutionProvider,
    MarketDataProvider,
    PortfolioProvider,
    StreamingProvider,
)
from tradex.core.health import HealthReport
from tradex.domain.account import AccountProfile, FundLimits
from tradex.domain.enums import (
    Exchange,
    InstrumentType,
    OrderType,
    ProductType,
    Side,
    Validity,
)
from tradex.domain.execution import Order
from tradex.domain.mapping import InstrumentMapper, SecurityMapping
from tradex.domain.market_data import MarketDepth, OptionChain, Quote

# ============================================================
# ABC Verification — All provider interfaces are ABCs
# ============================================================


class TestProviderABCs:
    def test_broker_provider_is_abc(self):
        assert issubclass(BrokerProvider, ABC)

    def test_auth_provider_is_abc(self):
        assert issubclass(AuthProvider, ABC)

    def test_execution_provider_is_abc(self):
        assert issubclass(ExecutionProvider, ABC)

    def test_market_data_provider_is_abc(self):
        assert issubclass(MarketDataProvider, ABC)

    def test_portfolio_provider_is_abc(self):
        assert issubclass(PortfolioProvider, ABC)

    def test_streaming_provider_is_abc(self):
        assert issubclass(StreamingProvider, ABC)


# ============================================================
# Abstract Method Verification — BrokerProvider
# ============================================================


class TestBrokerProviderAbstractMethods:
    def test_has_connect(self):
        assert hasattr(BrokerProvider, "connect")
        assert getattr(BrokerProvider.connect, "__isabstractmethod__", False)

    def test_has_disconnect(self):
        assert hasattr(BrokerProvider, "disconnect")
        assert getattr(BrokerProvider.disconnect, "__isabstractmethod__", False)

    def test_has_health(self):
        assert hasattr(BrokerProvider, "health")
        assert getattr(BrokerProvider.health, "__isabstractmethod__", False)

    def test_has_name_property(self):
        assert hasattr(BrokerProvider, "name")
        assert getattr(BrokerProvider.name, "__isabstractmethod__", False)

    def test_has_auth_property(self):
        assert hasattr(BrokerProvider, "auth")
        assert getattr(BrokerProvider.auth, "__isabstractmethod__", False)

    def test_has_execution_property(self):
        assert hasattr(BrokerProvider, "execution")
        assert getattr(BrokerProvider.execution, "__isabstractmethod__", False)

    def test_has_market_data_property(self):
        assert hasattr(BrokerProvider, "market_data")
        assert getattr(BrokerProvider.market_data, "__isabstractmethod__", False)

    def test_has_portfolio_property(self):
        assert hasattr(BrokerProvider, "portfolio")
        assert getattr(BrokerProvider.portfolio, "__isabstractmethod__", False)

    def test_has_streaming_property(self):
        assert hasattr(BrokerProvider, "streaming")
        assert getattr(BrokerProvider.streaming, "__isabstractmethod__", False)

    def test_has_mapper_property(self):
        assert hasattr(BrokerProvider, "mapper")
        assert getattr(BrokerProvider.mapper, "__isabstractmethod__", False)

    def test_has_get_capabilities(self):
        assert hasattr(BrokerProvider, "get_capabilities")
        assert getattr(BrokerProvider.get_capabilities, "__isabstractmethod__", False)


# ============================================================
# Abstract Method Verification — ExecutionProvider
# ============================================================


class TestExecutionProviderAbstractMethods:
    def test_has_place_order(self):
        assert getattr(ExecutionProvider.place_order, "__isabstractmethod__", False)

    def test_has_modify_order(self):
        assert getattr(ExecutionProvider.modify_order, "__isabstractmethod__", False)

    def test_has_cancel_order(self):
        assert getattr(ExecutionProvider.cancel_order, "__isabstractmethod__", False)

    def test_has_get_order(self):
        assert getattr(ExecutionProvider.get_order, "__isabstractmethod__", False)

    def test_has_get_orders(self):
        assert getattr(ExecutionProvider.get_orders, "__isabstractmethod__", False)

    def test_has_get_trades(self):
        assert getattr(ExecutionProvider.get_trades, "__isabstractmethod__", False)

    def test_has_get_trade_history(self):
        assert getattr(ExecutionProvider.get_trade_history, "__isabstractmethod__", False)


# ============================================================
# Abstract Method Verification — MarketDataProvider
# ============================================================


class TestMarketDataProviderAbstractMethods:
    def test_has_get_quote(self):
        assert getattr(MarketDataProvider.get_quote, "__isabstractmethod__", False)

    def test_has_get_quotes(self):
        assert getattr(MarketDataProvider.get_quotes, "__isabstractmethod__", False)

    def test_has_get_ohlcv(self):
        assert getattr(MarketDataProvider.get_ohlcv, "__isabstractmethod__", False)

    def test_has_get_minute_data(self):
        assert getattr(MarketDataProvider.get_minute_data, "__isabstractmethod__", False)

    def test_has_get_option_chain(self):
        assert getattr(MarketDataProvider.get_option_chain, "__isabstractmethod__", False)

    def test_has_get_expiry_list(self):
        assert getattr(MarketDataProvider.get_expiry_list, "__isabstractmethod__", False)

    def test_has_get_depth(self):
        assert getattr(MarketDataProvider.get_depth, "__isabstractmethod__", False)


# ============================================================
# Abstract Method Verification — PortfolioProvider
# ============================================================


class TestPortfolioProviderAbstractMethods:
    def test_has_get_holdings(self):
        assert getattr(PortfolioProvider.get_holdings, "__isabstractmethod__", False)

    def test_has_get_positions(self):
        assert getattr(PortfolioProvider.get_positions, "__isabstractmethod__", False)

    def test_has_get_fund_limits(self):
        assert getattr(PortfolioProvider.get_fund_limits, "__isabstractmethod__", False)

    def test_has_calculate_margin(self):
        assert getattr(PortfolioProvider.calculate_margin, "__isabstractmethod__", False)


# ============================================================
# Abstract Method Verification — StreamingProvider
# ============================================================


class TestStreamingProviderAbstractMethods:
    def test_has_connect(self):
        assert getattr(StreamingProvider.connect, "__isabstractmethod__", False)

    def test_has_disconnect(self):
        assert getattr(StreamingProvider.disconnect, "__isabstractmethod__", False)

    def test_has_subscribe(self):
        assert getattr(StreamingProvider.subscribe, "__isabstractmethod__", False)

    def test_has_unsubscribe(self):
        assert getattr(StreamingProvider.unsubscribe, "__isabstractmethod__", False)

    def test_has_ticks(self):
        assert getattr(StreamingProvider.ticks, "__isabstractmethod__", False)

    def test_has_is_connected(self):
        assert getattr(StreamingProvider.is_connected, "__isabstractmethod__", False)


# ============================================================
# Abstract Method Verification — AuthProvider
# ============================================================


class TestAuthProviderAbstractMethods:
    def test_has_connect(self):
        assert getattr(AuthProvider.connect, "__isabstractmethod__", False)

    def test_has_disconnect(self):
        assert getattr(AuthProvider.disconnect, "__isabstractmethod__", False)

    def test_has_refresh_token(self):
        assert getattr(AuthProvider.refresh_token, "__isabstractmethod__", False)

    def test_has_is_authenticated(self):
        assert getattr(AuthProvider.is_authenticated, "__isabstractmethod__", False)

    def test_has_get_profile(self):
        assert getattr(AuthProvider.get_profile, "__isabstractmethod__", False)


# ============================================================
# Cannot instantiate abstract classes
# ============================================================


class TestCannotInstantiateAbstracts:
    def test_cannot_instantiate_broker_provider(self):
        with pytest.raises(TypeError):
            BrokerProvider()  # type: ignore[abstract]

    def test_cannot_instantiate_auth_provider(self):
        with pytest.raises(TypeError):
            AuthProvider()  # type: ignore[abstract]

    def test_cannot_instantiate_execution_provider(self):
        with pytest.raises(TypeError):
            ExecutionProvider()  # type: ignore[abstract]

    def test_cannot_instantiate_market_data_provider(self):
        with pytest.raises(TypeError):
            MarketDataProvider()  # type: ignore[abstract]

    def test_cannot_instantiate_portfolio_provider(self):
        with pytest.raises(TypeError):
            PortfolioProvider()  # type: ignore[abstract]

    def test_cannot_instantiate_streaming_provider(self):
        with pytest.raises(TypeError):
            StreamingProvider()  # type: ignore[abstract]


# ============================================================
# Full Mock Implementation Conformance
# ============================================================


class TestMockImplementationConformance:
    """A complete mock implementation that satisfies the BrokerProvider contract."""

    def _build_mock(self):
        class FullMockAuthProvider(AuthProvider):
            async def connect(self):
                pass

            async def disconnect(self):
                pass

            async def refresh_token(self):
                pass

            async def is_authenticated(self):
                return True

            async def get_profile(self):
                return AccountProfile(client_id="mock")

        class FullMockExecutionProvider(ExecutionProvider):
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
                return Order(order_id="MOCK_1")

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
                return Order(order_id=order_id)

            async def cancel_order(self, order_id):
                pass

            async def get_order(self, order_id):
                return Order(order_id=order_id)

            async def get_orders(self):
                return []

            async def get_trades(self, order_id=None):
                return []

            async def get_trade_history(self, start_date, end_date, page=0):
                return []

        class FullMockMarketDataProvider(MarketDataProvider):
            async def get_quote(self, security_id, exchange):
                return Quote(security_id=security_id)

            async def get_quotes(self, securities):
                return {}

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
                return OptionChain()

            async def get_expiry_list(self, underlying_security_id, exchange):
                return []

            async def get_depth(self, security_id, exchange):
                return MarketDepth()

        class FullMockPortfolioProvider(PortfolioProvider):
            async def get_holdings(self):
                return []

            async def get_positions(self):
                return []

            async def get_fund_limits(self):
                return FundLimits()

            async def calculate_margin(
                self, security_id, exchange, side, quantity, product_type, price, trigger_price=0
            ):
                return {}

        class FullMockStreamingProvider(StreamingProvider):
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

        class FullMockInstrumentMapper(InstrumentMapper):
            def __init__(self):
                super().__init__("mock")

        class FullMockBrokerProvider(BrokerProvider):
            def __init__(self):
                self._auth = FullMockAuthProvider()
                self._execution = FullMockExecutionProvider()
                self._market_data = FullMockMarketDataProvider()
                self._portfolio = FullMockPortfolioProvider()
                self._streaming = FullMockStreamingProvider()
                self._mapper = FullMockInstrumentMapper()
                self._caps = CapabilityRegistry()

            @property
            def name(self):
                return "full_mock"

            async def connect(self):
                await self._auth.connect()

            async def disconnect(self):
                await self._auth.disconnect()

            async def health(self):
                return HealthReport()

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

            async def get_capabilities(self):
                return self._caps.names

        return FullMockBrokerProvider

    def test_mock_is_broker_provider(self):
        MockClass = self._build_mock()
        assert issubclass(MockClass, BrokerProvider)

    def test_mock_can_instantiate(self):
        MockClass = self._build_mock()
        instance = MockClass()
        assert instance.name == "full_mock"

    @pytest.mark.asyncio
    async def test_mock_connect_disconnect(self):
        MockClass = self._build_mock()
        provider = MockClass()
        await provider.connect()
        assert await provider.auth.is_authenticated()
        await provider.disconnect()

    @pytest.mark.asyncio
    async def test_mock_place_order(self):
        MockClass = self._build_mock()
        provider = MockClass()
        order = await provider.execution.place_order(
            security_id="2885",
            exchange_segment="NSE_EQ",
            side=Side.BUY,
            quantity=10,
            order_type=OrderType.MARKET,
            product_type=ProductType.INTRADAY,
            price=0,
        )
        assert isinstance(order, Order)
        assert order.order_id == "MOCK_1"

    @pytest.mark.asyncio
    async def test_mock_get_quote(self):
        MockClass = self._build_mock()
        provider = MockClass()
        quote = await provider.market_data.get_quote("2885", "NSE_EQ")
        assert isinstance(quote, Quote)
        assert quote.security_id == "2885"

    @pytest.mark.asyncio
    async def test_mock_portfolio(self):
        MockClass = self._build_mock()
        provider = MockClass()
        holdings = await provider.portfolio.get_holdings()
        assert isinstance(holdings, list)
        fl = await provider.portfolio.get_fund_limits()
        assert isinstance(fl, FundLimits)

    @pytest.mark.asyncio
    async def test_mock_streaming_lifecycle(self):
        MockClass = self._build_mock()
        provider = MockClass()
        assert not provider.streaming.is_connected
        await provider.streaming.connect()
        assert provider.streaming.is_connected
        await provider.streaming.disconnect()
        assert not provider.streaming.is_connected


# ============================================================
# BrokerExtension ABC
# ============================================================


class TestBrokerExtensionABC:
    def test_is_abc(self):
        assert issubclass(BrokerExtension, ABC)

    def test_has_abstract_name(self):
        assert getattr(BrokerExtension.name, "__isabstractmethod__", False)

    def test_has_abstract_description(self):
        assert getattr(BrokerExtension.description, "__isabstractmethod__", False)

    def test_has_abstract_execute(self):
        assert getattr(BrokerExtension.execute, "__isabstractmethod__", False)

    def test_validate_default_returns_true(self):
        """validate() has a default implementation returning True."""

        class TestExt(BrokerExtension):
            @property
            def name(self):
                return "test"

            @property
            def description(self):
                return "test ext"

            async def execute(self, **kwargs):
                return "done"

        ext = TestExt()
        loop = asyncio.new_event_loop()
        assert loop.run_until_complete(ext.validate(foo="bar"))
        loop.close()


# ============================================================
# CapabilityRegistry Contract
# ============================================================


class TestCapabilityRegistryContract:
    def test_register_and_query(self):
        reg = CapabilityRegistry()
        cap = BrokerCapability(name="test_cap", description="Test")
        reg.register(cap)
        assert reg.has("test_cap")
        assert reg.get("test_cap") is not None
        assert len(reg) == 1

    def test_register_many(self):
        reg = CapabilityRegistry()
        caps = [
            BrokerCapability(name="cap1"),
            BrokerCapability(name="cap2"),
            BrokerCapability(name="cap3"),
        ]
        reg.register_many(caps)
        assert len(reg) == 3
        assert reg.names == ["cap1", "cap2", "cap3"]

    def test_not_found(self):
        reg = CapabilityRegistry()
        assert not reg.has("nonexistent")
        assert reg.get("nonexistent") is None

    def test_get_parameter(self):
        reg = CapabilityRegistry()
        cap = BrokerCapability(name="depth", parameters={"max_levels": 20})
        reg.register(cap)
        assert reg.get_parameter("depth", "max_levels") == 20
        assert reg.get_parameter("depth", "missing", "default") == "default"
        assert reg.get_parameter("nonexistent", "key") is None

    def test_all_property(self):
        reg = CapabilityRegistry()
        reg.register(BrokerCapability(name="a"))
        reg.register(BrokerCapability(name="b"))
        assert len(reg.all) == 2

    def test_contains(self):
        reg = CapabilityRegistry()
        reg.register(BrokerCapability(name="x"))
        assert "x" in reg
        assert "y" not in reg


# ============================================================
# ExtensionRegistry Contract
# ============================================================


class TestExtensionRegistryContract:
    def test_register_and_get(self):
        caps = CapabilityRegistry()
        caps.register(BrokerCapability(name="my_ext"))

        reg = ExtensionRegistry(caps)

        class MyExt(BrokerExtension):
            @property
            def name(self):
                return "my_ext"

            @property
            def description(self):
                return "my extension"

            async def execute(self, **kwargs):
                return "result"

        ext = MyExt()
        reg.register(ext)

        got = reg.get("my_ext")
        assert got is not None

    def test_get_without_capability(self):
        caps = CapabilityRegistry()  # no capabilities
        reg = ExtensionRegistry(caps)

        class MyExt(BrokerExtension):
            @property
            def name(self):
                return "ext1"

            @property
            def description(self):
                return "ext"

            async def execute(self, **kwargs):
                return None

        reg.register(MyExt())
        # Not available because capability not registered
        assert reg.get("ext1") is None

    def test_execute(self):
        caps = CapabilityRegistry()
        caps.register(BrokerCapability(name="calc"))

        reg = ExtensionRegistry(caps)

        class CalcExt(BrokerExtension):
            @property
            def name(self):
                return "calc"

            @property
            def description(self):
                return "calc ext"

            async def execute(self, x=0, y=0):
                return x + y

        reg.register(CalcExt())

        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(reg.execute("calc", x=3, y=4))
        loop.close()
        assert result == 7

    def test_execute_not_found(self):
        caps = CapabilityRegistry()
        reg = ExtensionRegistry(caps)

        loop = asyncio.new_event_loop()
        with pytest.raises(ValueError, match="not found"):
            loop.run_until_complete(reg.execute("nonexistent"))
        loop.close()

    def test_available(self):
        caps = CapabilityRegistry()
        caps.register(BrokerCapability(name="a"))
        caps.register(BrokerCapability(name="b"))

        reg = ExtensionRegistry(caps)

        class ExtA(BrokerExtension):
            @property
            def name(self):
                return "a"

            @property
            def description(self):
                return "a"

            async def execute(self, **kwargs):
                pass

        class ExtB(BrokerExtension):
            @property
            def name(self):
                return "b"

            @property
            def description(self):
                return "b"

            async def execute(self, **kwargs):
                pass

        class ExtC(BrokerExtension):
            @property
            def name(self):
                return "c"

            @property
            def description(self):
                return "c"

            async def execute(self, **kwargs):
                pass

        reg.register(ExtA())
        reg.register(ExtB())
        reg.register(ExtC())

        assert set(reg.available) == {"a", "b"}  # "c" not in capabilities

    def test_contains(self):
        caps = CapabilityRegistry()
        caps.register(BrokerCapability(name="x"))

        reg = ExtensionRegistry(caps)

        class ExtX(BrokerExtension):
            @property
            def name(self):
                return "x"

            @property
            def description(self):
                return "x"

            async def execute(self, **kwargs):
                pass

        reg.register(ExtX())
        assert "x" in reg
        assert "y" not in reg


# ============================================================
# InstrumentMapper Contract
# ============================================================


class TestInstrumentMapperContract:
    @pytest.mark.asyncio
    async def test_load_and_resolve(self):
        class TestMapper(InstrumentMapper):
            def _parse_row(self, row):
                return SecurityMapping(
                    canonical_symbol=row["symbol"],
                    canonical_exchange=Exchange.NSE,
                    broker_security_id=row["sid"],
                    instrument_type=InstrumentType.EQUITY,
                )

        tm = TestMapper("test")
        await tm.load(
            [
                {"symbol": "RELIANCE", "sid": "2885"},
                {"symbol": "TCS", "sid": "1153"},
            ]
        )

        assert tm.is_loaded
        assert tm.count == 2

        mapping = await tm.resolve_by_symbol("RELIANCE", Exchange.NSE)
        assert mapping is not None
        assert mapping.broker_security_id == "2885"

    @pytest.mark.asyncio
    async def test_resolve_by_broker_id(self):
        class TestMapper(InstrumentMapper):
            def _parse_row(self, row):
                return SecurityMapping(
                    canonical_symbol=row["symbol"],
                    canonical_exchange=Exchange.NSE,
                    broker_security_id=row["sid"],
                )

        tm = TestMapper("test")
        await tm.load([{"symbol": "RELIANCE", "sid": "2885"}])

        mapping = await tm.resolve_by_broker_id("2885")
        assert mapping is not None
        assert mapping.canonical_symbol == "RELIANCE"

    @pytest.mark.asyncio
    async def test_refresh(self):
        class TestMapper(InstrumentMapper):
            def _parse_row(self, row):
                return SecurityMapping(
                    canonical_symbol=row["symbol"],
                    canonical_exchange=Exchange.NSE,
                    broker_security_id=row["sid"],
                )

        tm = TestMapper("test")
        await tm.load([{"symbol": "A", "sid": "1"}])
        assert tm.count == 1

        await tm.refresh([{"symbol": "B", "sid": "2"}])
        assert tm.count == 1
        mapping = await tm.resolve_by_symbol("B", Exchange.NSE)
        assert mapping is not None
        old = await tm.resolve_by_symbol("A", Exchange.NSE)
        assert old is None
