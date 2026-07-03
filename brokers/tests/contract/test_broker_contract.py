"""Contract tests — verify any broker adapter satisfies the BrokerGateway protocol.

These tests use a mock adapter to verify the protocol contract. Real adapters
(Dhan, Upstox, Paper) must also pass these tests.
"""

from __future__ import annotations

from decimal import Decimal


from brokers.domain import (
    Balance,
    MarketDepth,
    Order,
    OrderResponse,
    Quote,
    Side,
)
from brokers.domain.enums import OrderStatus
from brokers.ports import (
    BrokerGateway,
    InstrumentInfo,
)


class _FakeOrders:
    def place_order(self, symbol, exchange, side, quantity, **kwargs):
        return OrderResponse(order_id="ORD001", success=True)

    def cancel_order(self, order_id):
        return OrderResponse(order_id=order_id, success=True)

    def get_order(self, order_id):
        return Order(
            order_id=order_id,
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            status=OrderStatus.OPEN,
        )

    def get_orderbook(self):
        return []


class _FakeMarketData:
    def ltp(self, symbol, exchange="NSE"):
        return Decimal("2500.00")

    def quote(self, symbol, exchange="NSE"):
        return Quote(symbol=symbol, ltp=Decimal("2500.00"), exchange=exchange)

    def depth(self, symbol, exchange="NSE"):
        return MarketDepth(symbol=symbol)


class _FakePortfolio:
    def positions(self):
        return []

    def holdings(self):
        return []

    def funds(self):
        return Balance(available_cash=Decimal("50000.00"))

    def trades(self):
        return []


class _FakeInstruments:
    def search(self, query, limit=10):
        return [InstrumentInfo(symbol="RELIANCE", exchange="NSE")]

    def resolve(self, symbol, exchange="NSE"):
        return InstrumentInfo(symbol=symbol, exchange=exchange)

    def load(self):
        pass


class _FakeAuth:
    def get_token(self):
        return "fake-token"

    def refresh_token(self):
        return "refreshed-token"

    def is_authenticated(self):
        return True


class _FakeHistorical:
    def get_historical_candles(
        self, symbol, exchange, start_time, end_time, resolution
    ):
        return []


class _FakeStreaming:
    async def connect(self):
        pass

    async def disconnect(self):
        pass

    @property
    def is_connected(self):
        return True

    async def subscribe_quotes(self, symbols, exchange, callback):
        pass

    async def unsubscribe_quotes(self, symbols, exchange):
        pass


class _FakeBroker:
    def __init__(self):
        self._orders = _FakeOrders()
        self._market_data = _FakeMarketData()
        self._portfolio = _FakePortfolio()
        self._instruments = _FakeInstruments()
        self._auth = _FakeAuth()
        self._historical = _FakeHistorical()
        self._streaming = _FakeStreaming()

    @property
    def broker_id(self):
        return "fake"

    def capabilities(self):
        return None

    @property
    def orders(self):
        return self._orders

    @property
    def market_data(self):
        return self._market_data

    @property
    def portfolio(self):
        return self._portfolio

    @property
    def instruments(self):
        return self._instruments

    @property
    def auth(self):
        return self._auth

    @property
    def historical(self):
        return self._historical

    @property
    def streaming(self):
        return self._streaming

    @property
    def options(self):
        return None

    @property
    def extensions(self):
        from brokers.ports.extension_registry import DictExtensionRegistry
        return DictExtensionRegistry()

    def close(self):
        pass


class TestBrokerGatewayContract:
    def test_satisfies_protocol(self):
        gw = _FakeBroker()
        assert isinstance(gw, BrokerGateway)

    def test_place_order(self):
        gw = _FakeBroker()
        resp = gw.orders.place_order("RELIANCE", "NSE", Side.BUY, 10)
        assert resp.success
        assert resp.order_id == "ORD001"

    def test_cancel_order(self):
        gw = _FakeBroker()
        resp = gw.orders.cancel_order("ORD001")
        assert resp.success

    def test_get_order(self):
        gw = _FakeBroker()
        order = gw.orders.get_order("ORD001")
        assert order is not None
        assert order.order_id == "ORD001"

    def test_get_orderbook(self):
        gw = _FakeBroker()
        assert isinstance(gw.orders.get_orderbook(), list)

    def test_ltp(self):
        gw = _FakeBroker()
        price = gw.market_data.ltp("RELIANCE")
        assert price == Decimal("2500.00")

    def test_quote(self):
        gw = _FakeBroker()
        q = gw.market_data.quote("RELIANCE")
        assert q.symbol == "RELIANCE"
        assert q.ltp == Decimal("2500.00")

    def test_depth(self):
        gw = _FakeBroker()
        d = gw.market_data.depth("RELIANCE")
        assert d.symbol == "RELIANCE"

    def test_positions(self):
        gw = _FakeBroker()
        assert isinstance(gw.portfolio.positions(), list)

    def test_holdings(self):
        gw = _FakeBroker()
        assert isinstance(gw.portfolio.holdings(), list)

    def test_funds(self):
        gw = _FakeBroker()
        bal = gw.portfolio.funds()
        assert bal.available_cash == Decimal("50000.00")

    def test_trades(self):
        gw = _FakeBroker()
        assert isinstance(gw.portfolio.trades(), list)

    def test_search_instruments(self):
        gw = _FakeBroker()
        results = gw.instruments.search("REL")
        assert len(results) == 1
        assert results[0].symbol == "RELIANCE"

    def test_resolve_instrument(self):
        gw = _FakeBroker()
        info = gw.instruments.resolve("RELIANCE")
        assert info is not None
        assert info.symbol == "RELIANCE"

    def test_auth(self):
        gw = _FakeBroker()
        assert gw.auth.is_authenticated()
        assert gw.auth.get_token() == "fake-token"

    def test_close(self):
        gw = _FakeBroker()
        gw.close()
