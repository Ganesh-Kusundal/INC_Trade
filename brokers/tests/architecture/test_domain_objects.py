"""Unit tests for the v2 rich domain objects.

Tests behavior of Instrument, Account, Order, and OptionChain — verifying
they are rich domain objects with real behavior, not anemic data bags.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from brokers.domain.enums import AssetClass, Exchange, OptionType, OrderStatus, Side
from brokers.domain.instrument import InstrumentIdentity
from brokers.domain.order import InvalidOrderTransitionError, Order
from brokers.domain.requests import OrderRequest
from brokers.domain.values import OrderResponse


# ── Test fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def paper_broker():
    """Create a paper broker for testing."""
    from brokers import Broker
    return Broker.paper()


@pytest.fixture
def reliance(paper_broker):
    """Create a RELIANCE instrument via the paper broker."""
    return paper_broker.instrument("RELIANCE", Exchange.NSE)


# ── Instrument identity tests ──────────────────────────────────────────────


class TestInstrumentIdentity:
    """Test immutable identity and computed properties."""

    def test_identity_is_immutable(self) -> None:
        identity = InstrumentIdentity(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            asset_class=AssetClass.EQUITY,
        )
        assert identity.symbol == "RELIANCE"
        assert identity.exchange == Exchange.NSE
        # Frozen dataclass — should raise on setattr
        with pytest.raises(AttributeError):
            identity.symbol = "TCS"  # type: ignore[misc]

    def test_identity_hashable(self) -> None:
        id1 = InstrumentIdentity(symbol="RELIANCE", exchange=Exchange.NSE)
        id2 = InstrumentIdentity(symbol="RELIANCE", exchange=Exchange.NSE)
        assert hash(id1) == hash(id2)
        assert id1 == id2

    def test_instrument_key(self) -> None:
        from brokers import Broker
        broker = Broker.paper()
        inst = broker.instrument("RELIANCE", Exchange.NSE)
        assert inst.key == "RELIANCE:NSE"

    def test_derivative_properties(self) -> None:
        from brokers import Broker
        broker = Broker.paper()
        equity = broker.instrument("RELIANCE", Exchange.NSE)
        assert equity.is_equity
        assert not equity.is_derivative

        option = broker.instrument(
            "NIFTY24JUL25000CE",
            Exchange.NFO,
            asset_class=AssetClass.OPTION,
            expiry=date(2026, 7, 31),
            strike=Decimal("25000"),
            option_type=OptionType.CALL,
        )
        assert option.is_option
        assert option.is_derivative
        assert not option.is_expired  # expiry is in the future

    def test_expired_option(self) -> None:
        from brokers import Broker
        broker = Broker.paper()
        expired = broker.instrument(
            "NIFTY24JAN25000CE",
            Exchange.NFO,
            asset_class=AssetClass.OPTION,
            expiry=date(2020, 1, 1),  # Past expiry
            strike=Decimal("25000"),
            option_type=OptionType.CALL,
        )
        assert expired.is_expired


# ── Instrument market data tests ──────────────────────────────────────────


class TestInstrumentMarketData:
    """Test that Instrument delegates IO to provider and caches results."""

    @pytest.mark.asyncio
    async def test_quote(self, reliance) -> None:
        quote = await reliance.quote()
        assert quote.symbol == "RELIANCE"
        assert quote.ltp > 0

    @pytest.mark.asyncio
    async def test_ltp(self, reliance) -> None:
        ltp = await reliance.ltp()
        assert ltp == Decimal("2550.00")  # Paper default

    @pytest.mark.asyncio
    async def test_depth(self, reliance) -> None:
        depth = await reliance.depth()
        assert depth.symbol == "RELIANCE"
        assert len(depth.bids) > 0
        assert len(depth.asks) > 0

    @pytest.mark.asyncio
    async def test_history(self, reliance) -> None:
        series = await reliance.history(timeframe="1D", bars=5)
        assert series.bar_count == 5
        assert series.symbol == "RELIANCE"

    @pytest.mark.asyncio
    async def test_cached_quote(self, reliance) -> None:
        # Before calling quote(), cached_quote is None
        assert reliance.cached_quote is None
        await reliance.quote()
        # After calling quote(), cached_quote is set
        assert reliance.cached_quote is not None
        assert reliance.cached_quote.symbol == "RELIANCE"


# ── Instrument trading tests ──────────────────────────────────────────────


class TestInstrumentTrading:
    """Test that Instrument.buy()/sell() delegates to Account."""

    @pytest.mark.asyncio
    async def test_buy(self, reliance) -> None:
        response = await reliance.buy(quantity=10)
        assert response.success
        assert response.order_id.startswith("paper_")

    @pytest.mark.asyncio
    async def test_sell(self, reliance) -> None:
        response = await reliance.sell(quantity=5)
        assert response.success

    @pytest.mark.asyncio
    async def test_buy_with_account(self, paper_broker, reliance) -> None:
        account = paper_broker.account()
        response = await reliance.buy(quantity=10, account=account)
        assert response.success
        # Account should track the order
        assert response.order_id in account.open_orders


# ── Account tests ─────────────────────────────────────────────────────────


class TestAccount:
    """Test Account aggregate root with risk gating."""

    @pytest.mark.asyncio
    async def test_place_order(self, paper_broker) -> None:
        account = paper_broker.account()
        request = OrderRequest(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            side=Side.BUY,
            quantity=10,
        )
        response = await account.place_order(request)
        assert response.success
        assert response.order_id in account.open_orders

    @pytest.mark.asyncio
    async def test_get_positions(self, paper_broker) -> None:
        account = paper_broker.account()
        # Place an order first
        await account.place_order(OrderRequest(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            side=Side.BUY,
            quantity=10,
        ))
        positions = await account.get_positions()
        assert len(positions) > 0
        assert positions[0].symbol == "RELIANCE"

    @pytest.mark.asyncio
    async def test_get_balance(self, paper_broker) -> None:
        account = paper_broker.account()
        balance = await account.get_balance()
        assert balance.available_balance > 0

    @pytest.mark.asyncio
    async def test_risk_policy_no_limits(self, paper_broker) -> None:
        """No-limits risk policy allows all orders."""
        from brokers import RiskPolicy
        from brokers.broker import Broker

        broker = Broker.paper(risk_policy=RiskPolicy.no_limits())
        account = broker.account()
        response = await account.place_order(OrderRequest(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            side=Side.BUY,
            quantity=1000000,  # Huge order
        ))
        assert response.success  # No limits → allowed

    @pytest.mark.asyncio
    async def test_risk_policy_max_position(self) -> None:
        """Max position risk policy blocks oversized orders."""
        from brokers import Broker, RiskPolicy

        broker = Broker.paper(risk_policy=RiskPolicy.max_position(max_quantity=100))
        account = broker.account()
        response = await account.place_order(OrderRequest(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            side=Side.BUY,
            quantity=200,  # Exceeds max
        ))
        assert not response.success
        assert "Risk denied" in response.message


# ── Order lifecycle tests ─────────────────────────────────────────────────


class TestOrderLifecycle:
    """Test Order entity state machine."""

    def test_order_creation(self) -> None:
        request = OrderRequest(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            side=Side.BUY,
            quantity=10,
        )
        response = OrderResponse.ok(order_id="test_1", status=OrderStatus.OPEN)
        order = Order(request, response)
        assert order.order_id == "test_1"
        assert order.status == OrderStatus.OPEN
        assert order.is_open

    def test_valid_transition(self) -> None:
        request = OrderRequest(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            side=Side.BUY,
            quantity=10,
        )
        response = OrderResponse.ok(order_id="test_2", status=OrderStatus.OPEN)
        order = Order(request, response)
        order.update_status(OrderStatus.FILLED, filled_quantity=10)
        assert order.status == OrderStatus.FILLED
        assert order.is_terminal

    def test_invalid_transition(self) -> None:
        request = OrderRequest(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            side=Side.BUY,
            quantity=10,
        )
        response = OrderResponse.ok(order_id="test_3", status=OrderStatus.FILLED)
        order = Order(request, response)
        # FILLED → OPEN is invalid
        with pytest.raises(InvalidOrderTransitionError):
            order.update_status(OrderStatus.OPEN)

    def test_remaining_quantity(self) -> None:
        request = OrderRequest(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            side=Side.BUY,
            quantity=100,
        )
        response = OrderResponse.ok(order_id="test_4", status=OrderStatus.PARTIALLY_FILLED)
        order = Order(request, response)
        order.update_status(OrderStatus.PARTIALLY_FILLED, filled_quantity=30)
        assert order.remaining_quantity == 70


# ── OptionChain tests ─────────────────────────────────────────────────────


class TestOptionChain:
    """Test OptionChain aggregate root."""

    @pytest.mark.asyncio
    async def test_option_chain(self, paper_broker) -> None:
        nifty = paper_broker.instrument("NIFTY", Exchange.NFO, asset_class=AssetClass.INDEX)
        chain = await nifty.option_chain()
        assert chain.contract_count > 0
        assert len(chain.strikes) > 0
        assert len(chain.expiries) > 0

    @pytest.mark.asyncio
    async def test_option_chain_calls_puts(self, paper_broker) -> None:
        nifty = paper_broker.instrument("NIFTY", Exchange.NFO, asset_class=AssetClass.INDEX)
        chain = await nifty.option_chain()
        calls = chain.calls()
        puts = chain.puts()
        assert len(calls) > 0
        assert len(puts) > 0

    @pytest.mark.asyncio
    async def test_option_chain_atm(self, paper_broker) -> None:
        nifty = paper_broker.instrument("NIFTY", Exchange.NFO, asset_class=AssetClass.INDEX)
        chain = await nifty.option_chain()
        spot = await nifty.ltp()
        atm = chain.atm(spot=spot)
        assert atm is not None
        # ATM should be the closest strike to spot
        assert abs(atm.strike - spot) == min(abs(s.strike - spot) for s in chain.contracts)

    @pytest.mark.asyncio
    async def test_option_chain_itm_otm(self, paper_broker) -> None:
        nifty = paper_broker.instrument("NIFTY", Exchange.NFO, asset_class=AssetClass.INDEX)
        chain = await nifty.option_chain()
        spot = await nifty.ltp()
        itm_calls = chain.itm_calls(spot=spot)
        otm_calls = chain.otm_calls(spot=spot)
        # ITM calls have strike < spot, OTM calls have strike > spot
        for c in itm_calls:
            assert c.strike < spot
        for c in otm_calls:
            assert c.strike > spot

    @pytest.mark.asyncio
    async def test_future_chain(self, paper_broker) -> None:
        nifty = paper_broker.instrument("NIFTY", Exchange.NFO, asset_class=AssetClass.INDEX)
        chain = await nifty.future_chain()
        assert chain.contract_count > 0
        near = chain.near_month()
        assert near is not None


# ── Broker factory tests ──────────────────────────────────────────────────


class TestBrokerFactory:
    """Test Broker factory and DI."""

    def test_paper_broker(self) -> None:
        from brokers import Broker
        broker = Broker.paper()
        assert broker.broker_id == "paper"
        assert not broker.is_connected  # Not connected yet

    @pytest.mark.asyncio
    async def test_connect_disconnect(self) -> None:
        from brokers import Broker
        broker = Broker.paper()
        await broker.connect()
        assert broker.is_connected
        await broker.disconnect()
        assert not broker.is_connected

    def test_instrument_creation(self) -> None:
        from brokers import Broker
        broker = Broker.paper()
        inst = broker.instrument("RELIANCE", Exchange.NSE)
        assert inst.symbol == "RELIANCE"
        assert inst.exchange == Exchange.NSE
        assert inst.provider is broker.provider

    def test_account_creation(self) -> None:
        from brokers import Broker
        broker = Broker.paper()
        account = broker.account()
        assert account.account_id == "paper_default"
        assert account.provider is broker.provider
