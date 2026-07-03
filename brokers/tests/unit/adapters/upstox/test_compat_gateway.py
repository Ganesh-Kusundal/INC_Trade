"""Unit tests for Upstox compatibility gateway."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

from brokers.adapters.upstox.compat_gateway import UpstoxCompatibilityGateway
from brokers.adapters.upstox.gateway import UpstoxGateway
from brokers.domain import Balance, Holding, MarketDepth, Order, OrderResponse, Position, Quote, Trade
from brokers.domain.enums import OrderType, ProductType, Side, Validity


class TestUpstoxCompatGateway:
    @patch("brokers.adapters.upstox.gateway.UpstoxStreaming")
    def test_delegates_ltp(self, mock_streaming):
        gw = UpstoxGateway(access_token="tok")
        compat = UpstoxCompatibilityGateway(gw)
        gw.market_data.ltp = MagicMock(return_value=100)
        assert compat.ltp("RELIANCE") == 100
        gw.close()

    @patch("brokers.adapters.upstox.gateway.UpstoxStreaming")
    def test_orderbook_alias(self, mock_streaming):
        gw = UpstoxGateway(access_token="tok")
        compat = UpstoxCompatibilityGateway(gw)
        gw.orders.get_orderbook = MagicMock(return_value=[])
        assert compat.orderbook() == []
        gw.close()


class TestCompatGatewayMockBased:
    def setup_method(self):
        self.inner = MagicMock()
        self.gw = UpstoxCompatibilityGateway(self.inner)

    def test_place_order_string_to_enum(self):
        resp = OrderResponse(order_id="123", success=True)
        self.inner.orders.place_order.return_value = resp
        result = self.gw.place_order(
            symbol="RELIANCE",
            exchange="NSE",
            side="BUY",
            quantity=10,
            price=Decimal("2500"),
            order_type="LIMIT",
            product_type="DELIVERY",
            validity="DAY",
            trigger_price=Decimal("0"),
            correlation_id="abc",
        )
        self.inner.orders.place_order.assert_called_once_with(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            order_type=OrderType.LIMIT,
            price=Decimal("2500"),
            product_type=ProductType.DELIVERY,
            validity=Validity.DAY,
            trigger_price=Decimal("0"),
            correlation_id="abc",
        )
        assert result.order_id == "123"

    def test_place_order_enum_passthrough(self):
        self.inner.orders.place_order.return_value = OrderResponse(order_id="456", success=True)
        result = self.gw.place_order(
            symbol="TCS",
            side=Side.SELL,
            order_type=OrderType.MARKET,
            product_type=ProductType.INTRADAY,
            validity=Validity.DAY,
        )
        assert result.order_id == "456"

    def test_cancel_order(self):
        resp = OrderResponse(order_id="100", success=True)
        self.inner.orders.cancel_order.return_value = resp
        result = self.gw.cancel_order("100")
        self.inner.orders.cancel_order.assert_called_once_with("100")
        assert result.order_id == "100"

    def test_modify_order(self):
        resp = OrderResponse(order_id="200", success=True)
        self.inner.orders.modify_order.return_value = resp
        result = self.gw.modify_order("200", quantity=20)
        self.inner.orders.modify_order.assert_called_once_with("200", quantity=20)
        assert result.order_id == "200"

    def test_get_order(self):
        order = MagicMock(spec=Order)
        self.inner.orders.get_order.return_value = order
        result = self.gw.get_order("300")
        self.inner.orders.get_order.assert_called_once_with("300")
        assert result is order

    def test_get_order_returns_none(self):
        self.inner.orders.get_order.return_value = None
        assert self.gw.get_order("999") is None

    def test_get_orderbook(self):
        self.inner.orders.get_orderbook.return_value = ["o1", "o2"]
        result = self.gw.get_orderbook()
        self.inner.orders.get_orderbook.assert_called_once()
        assert result == ["o1", "o2"]

    def test_ltp(self):
        self.inner.market_data.ltp.return_value = Decimal("2500")
        result = self.gw.ltp("RELIANCE", "NSE")
        self.inner.market_data.ltp.assert_called_once_with("RELIANCE", "NSE")
        assert result == Decimal("2500")

    def test_quote(self):
        q = MagicMock(spec=Quote)
        self.inner.market_data.quote.return_value = q
        result = self.gw.quote("RELIANCE", "NSE")
        self.inner.market_data.quote.assert_called_once_with("RELIANCE", "NSE")
        assert result is q

    def test_depth(self):
        d = MagicMock(spec=MarketDepth)
        self.inner.market_data.depth.return_value = d
        result = self.gw.depth("RELIANCE", "NSE")
        self.inner.market_data.depth.assert_called_once_with("RELIANCE", "NSE")
        assert result is d

    def test_ltp_batch(self):
        expected = {"RELIANCE": Decimal("2500"), "TCS": Decimal("3500")}
        self.inner.ltp_batch.return_value = expected
        result = self.gw.ltp_batch(["RELIANCE", "TCS"], "NSE")
        self.inner.ltp_batch.assert_called_once_with(["RELIANCE", "TCS"], "NSE")
        assert result == expected

    def test_quote_batch(self):
        expected = {"RELIANCE": MagicMock(), "TCS": MagicMock()}
        self.inner.quote_batch.return_value = expected
        result = self.gw.quote_batch(["RELIANCE", "TCS"], "NSE")
        self.inner.quote_batch.assert_called_once_with(["RELIANCE", "TCS"], "NSE")
        assert result == expected

    def test_positions(self):
        self.inner.portfolio.positions.return_value = ["p1"]
        result = self.gw.positions()
        self.inner.portfolio.positions.assert_called_once()
        assert result == ["p1"]

    def test_holdings(self):
        self.inner.portfolio.holdings.return_value = ["h1"]
        result = self.gw.holdings()
        self.inner.portfolio.holdings.assert_called_once()
        assert result == ["h1"]

    def test_funds(self):
        bal = MagicMock(spec=Balance)
        self.inner.portfolio.funds.return_value = bal
        result = self.gw.funds()
        self.inner.portfolio.funds.assert_called_once()
        assert result is bal

    def test_trades(self):
        self.inner.portfolio.trades.return_value = ["t1", "t2"]
        result = self.gw.trades()
        self.inner.portfolio.trades.assert_called_once()
        assert result == ["t1", "t2"]

    def test_get_trade_book_delegates_to_trades(self):
        self.inner.portfolio.trades.return_value = ["t1"]
        result = self.gw.get_trade_book()
        self.inner.portfolio.trades.assert_called_once()
        assert result == ["t1"]

    def test_load_instruments(self):
        self.gw.load_instruments(source="/path/to/file")
        self.inner.load_instruments.assert_called_once_with(source="/path/to/file")

    def test_load_instruments_no_source(self):
        self.gw.load_instruments()
        self.inner.load_instruments.assert_called_once_with(source=None)

    def test_stream_mode_mapping(self):
        self.inner.streaming.is_connected = True
        handle = self.gw.stream("RELIANCE", "NSE", mode="LTP")
        assert self.inner.streaming.mode == "ltpc"
        self.inner.streaming.subscribe.assert_called_once_with("RELIANCE", "NSE")

    def test_stream_full_mode(self):
        self.inner.streaming.is_connected = True
        self.gw.stream("RELIANCE", "NSE", mode="FULL")
        assert self.inner.streaming.mode == "full"

    def test_stream_lowercase_ltp(self):
        self.inner.streaming.is_connected = True
        self.gw.stream("RELIANCE", "NSE", mode="ltp")
        assert self.inner.streaming.mode == "ltpc"

    def test_stream_starts_if_not_connected(self):
        self.inner.streaming.is_connected = False
        self.gw.stream("RELIANCE", "NSE")
        self.inner.streaming.start.assert_called_once()

    def test_stream_does_not_start_if_connected(self):
        self.inner.streaming.is_connected = True
        self.gw.stream("RELIANCE", "NSE")
        self.inner.streaming.start.assert_not_called()

    def test_stream_sets_on_tick(self):
        cb = MagicMock()
        self.inner.streaming.is_connected = True
        self.gw.stream("RELIANCE", "NSE", on_tick=cb)
        assert self.inner.streaming.on_tick is cb

    def test_unstream(self):
        self.gw.unstream("RELIANCE", "NSE")
        self.inner.streaming.unsubscribe.assert_called_once_with("RELIANCE", "NSE")

    def test_stream_depth(self):
        self.gw.stream_depth("RELIANCE", "NSE", "DEPTH_5", MagicMock())
        self.inner.stream_depth.assert_called_once()

    def test_option_chain(self):
        self.inner.option_chain.return_value = {"CE": [], "PE": []}
        result = self.gw.option_chain("NIFTY", "NFO", "2025-01-30")
        self.inner.option_chain.assert_called_once_with("NIFTY", "NFO", "2025-01-30")
        assert result == {"CE": [], "PE": []}

    def test_close(self):
        self.gw.close()
        self.inner.close.assert_called_once()

    def test_inner_property(self):
        assert self.gw.inner is self.inner
