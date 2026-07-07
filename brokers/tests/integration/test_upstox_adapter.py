"""Integration tests for Upstox adapter — uses mocked HTTP responses."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

from brokers.domain import Side
from brokers.domain.enums import OrderStatus, OrderType

from brokers.adapters.upstox.gateway import UpstoxGateway


def _mock_response(json_data, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = str(json_data)
    return resp


class TestUpstoxOrders:
    @patch("brokers.adapters.upstox.http.requests.Session")
    def test_place_order(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session.request.return_value = _mock_response(
            {
                "status": "success",
                "data": {"order_id": "240715000001"},
            }
        )
        mock_session.headers = {}
        mock_session_cls.return_value = mock_session

        gw = UpstoxGateway(access_token="tok")
        resp = gw.orders.place_order("RELIANCE", "NSE", Side.BUY, 10)
        assert resp.success
        assert resp.order_id == "240715000001"
        gw.close()

    @patch("brokers.adapters.upstox.http.requests.Session")
    def test_place_order_with_limit_price(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session.request.return_value = _mock_response(
            {
                "status": "success",
                "data": {"order_id": "240715000002"},
            }
        )
        mock_session.headers = {}
        mock_session_cls.return_value = mock_session

        gw = UpstoxGateway(access_token="tok")
        resp = gw.orders.place_order(
            "RELIANCE",
            "NSE",
            Side.BUY,
            10,
            order_type=OrderType.LIMIT,
            price=Decimal("2500.50"),
        )
        assert resp.success
        call_args = mock_session.request.call_args
        payload = call_args.kwargs.get("json", {})
        assert payload["order_type"] == "LIMIT"
        assert payload["price"] == 2500.50
        gw.close()

    @patch("brokers.adapters.upstox.http.requests.Session")
    def test_cancel_order(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session.request.return_value = _mock_response(
            {
                "status": "success",
            }
        )
        mock_session.headers = {}
        mock_session_cls.return_value = mock_session

        gw = UpstoxGateway(access_token="tok")
        resp = gw.orders.cancel_order("240715000001")
        assert resp.success
        gw.close()

    @patch("brokers.adapters.upstox.http.requests.Session")
    def test_get_orderbook(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session.request.return_value = _mock_response(
            {
                "data": [
                    {
                        "order_id": "1",
                        "trading_symbol": "RELIANCE",
                        "status": "OPEN",
                        "transaction_type": "BUY",
                        "quantity": 10,
                        "exchange": "NSE",
                    },
                    {
                        "order_id": "2",
                        "trading_symbol": "TCS",
                        "status": "COMPLETE",
                        "transaction_type": "SELL",
                        "quantity": 5,
                        "exchange": "NSE",
                    },
                ]
            }
        )
        mock_session.headers = {}
        mock_session_cls.return_value = mock_session

        gw = UpstoxGateway(access_token="tok")
        book = gw.orders.get_orderbook()
        assert len(book) == 2
        assert book[0].symbol == "RELIANCE"
        assert book[1].status == OrderStatus.FILLED
        gw.close()


class TestUpstoxMarketData:
    @patch("brokers.adapters.upstox.http.requests.Session")
    def test_ltp(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session.request.return_value = _mock_response(
            {"data": {"NSE_EQ|RELIANCE": {"last_price": 2500.0}}}
        )
        mock_session.headers = {}
        mock_session_cls.return_value = mock_session

        gw = UpstoxGateway(access_token="tok")
        price = gw.market_data.ltp("RELIANCE")
        assert price == Decimal("2500.0")
        gw.close()

    @patch("brokers.adapters.upstox.http.requests.Session")
    def test_quote(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session.request.return_value = _mock_response(
            {
                "data": {
                    "NSE_EQ|RELIANCE": {
                        "last_price": 2500.0,
                        "volume": 100000,
                        "ohlc": {
                            "open": 2480,
                            "high": 2520,
                            "low": 2470,
                            "close": 2490,
                        },
                    }
                }
            }
        )
        mock_session.headers = {}
        mock_session_cls.return_value = mock_session

        gw = UpstoxGateway(access_token="tok")
        q = gw.market_data.quote("RELIANCE")
        assert q.symbol == "RELIANCE"
        assert q.ltp == Decimal("2500.0")
        assert q.volume == 100000
        assert q.open == Decimal("2480")
        gw.close()

    @patch("brokers.adapters.upstox.http.requests.Session")
    def test_depth(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session.request.return_value = _mock_response(
            {
                "data": {
                    "NSE_EQ|RELIANCE": {
                        "depth": {
                            "buy": [{"price": 2499, "quantity": 100, "orders": 5}],
                            "sell": [{"price": 2501, "quantity": 200, "orders": 3}],
                        }
                    }
                }
            }
        )
        mock_session.headers = {}
        mock_session_cls.return_value = mock_session

        gw = UpstoxGateway(access_token="tok")
        d = gw.market_data.depth("RELIANCE")
        assert len(d.bids) == 1
        assert d.bids[0].price == Decimal("2499")
        assert len(d.asks) == 1
        assert d.asks[0].quantity == 200
        gw.close()


class TestUpstoxPortfolio:
    @patch("brokers.adapters.upstox.http.requests.Session")
    def test_positions(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session.request.return_value = _mock_response(
            {
                "data": [
                    {
                        "trading_symbol": "RELIANCE",
                        "exchange": "NSE",
                        "net_quantity": 10,
                        "product": "I",
                    },
                ]
            }
        )
        mock_session.headers = {}
        mock_session_cls.return_value = mock_session

        gw = UpstoxGateway(access_token="tok")
        positions = gw.portfolio.positions()
        assert len(positions) == 1
        assert positions[0].symbol == "RELIANCE"
        assert positions[0].quantity == 10
        gw.close()

    @patch("brokers.adapters.upstox.http.requests.Session")
    def test_holdings(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session.request.return_value = _mock_response(
            {
                "data": [
                    {
                        "trading_symbol": "TCS",
                        "exchange": "NSE",
                        "quantity": 50,
                        "average_price": 3500,
                        "isin": "INE467B01029",
                    },
                ]
            }
        )
        mock_session.headers = {}
        mock_session_cls.return_value = mock_session

        gw = UpstoxGateway(access_token="tok")
        holdings = gw.portfolio.holdings()
        assert len(holdings) == 1
        assert holdings[0].symbol == "TCS"
        assert holdings[0].isin == "INE467B01029"
        gw.close()

    @patch("brokers.adapters.upstox.http.requests.Session")
    def test_funds(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session.request.return_value = _mock_response(
            {
                "data": {
                    "equity": {
                        "available_margin": 50000.0,
                        "used_margin": 10000.0,
                        "net_margin": 60000.0,
                    }
                }
            }
        )
        mock_session.headers = {}
        mock_session_cls.return_value = mock_session

        gw = UpstoxGateway(access_token="tok")
        bal = gw.portfolio.funds()
        assert bal.available_cash == Decimal("50000.0")
        assert bal.utilized_margin == Decimal("10000.0")
        gw.close()

    @patch("brokers.adapters.upstox.http.requests.Session")
    def test_trades(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session.request.return_value = _mock_response(
            {
                "data": [
                    {
                        "trade_id": "T1",
                        "order_id": "O1",
                        "trading_symbol": "RELIANCE",
                        "exchange": "NSE",
                        "transaction_type": "BUY",
                        "quantity": 10,
                        "average_price": 2500,
                    },
                ]
            }
        )
        mock_session.headers = {}
        mock_session_cls.return_value = mock_session

        gw = UpstoxGateway(access_token="tok")
        trades = gw.portfolio.trades()
        assert len(trades) == 1
        assert trades[0].trade_id == "T1"
        assert trades[0].price == Decimal("2500")
        gw.close()


class TestUpstoxAuth:
    def test_is_authenticated(self):
        gw = UpstoxGateway(access_token="tok")
        assert gw.auth.is_authenticated()
        assert gw.auth.get_token() == "tok"
        gw.close()

    @patch(
        "brokers.adapters.upstox.gateway.UpstoxSettingsLoader.from_env",
        side_effect=ValueError("no env"),
    )
    def test_not_authenticated_without_token(self, _mock_env):
        gw = UpstoxGateway(access_token="")
        assert not gw.auth.is_authenticated()
        gw.close()


class TestUpstoxInstrumentKey:
    @patch("brokers.adapters.upstox.http.requests.Session")
    def test_instrument_key_format(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session.request.return_value = _mock_response(
            {
                "status": "success",
                "data": {"order_id": "123"},
            }
        )
        mock_session.headers = {}
        mock_session_cls.return_value = mock_session

        gw = UpstoxGateway(access_token="tok")
        gw.orders.place_order("RELIANCE", "NSE", Side.BUY, 10)

        call_args = mock_session.request.call_args
        payload = call_args.kwargs.get("json", {})
        assert payload["instrument_token"] == "NSE_EQ|RELIANCE"
        gw.close()

    @patch("brokers.adapters.upstox.http.requests.Session")
    def test_fno_instrument_key(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session.request.return_value = _mock_response(
            {
                "status": "success",
                "data": {"order_id": "124"},
            }
        )
        mock_session.headers = {}
        mock_session_cls.return_value = mock_session

        gw = UpstoxGateway(access_token="tok")
        gw.orders.place_order("NIFTY 24000 CE", "NFO", Side.BUY, 50)

        call_args = mock_session.request.call_args
        payload = call_args.kwargs.get("json", {})
        assert payload["instrument_token"] == "NSE_FO|NIFTY 24000 CE"
        gw.close()
