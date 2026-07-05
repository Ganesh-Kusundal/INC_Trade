"""Integration tests for Dhan adapter — uses mocked HTTP responses."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from brokers.adapters.dhan.gateway import DhanGateway
from brokers.adapters.dhan.identity import DhanInstrumentRef
from inc_trade.domain import Side
from inc_trade.infrastructure.totp_cooldown import TOTPCooldown
from inc_trade.ports import BrokerGateway


@pytest.fixture(autouse=True)
def _isolated_totp_cooldown(tmp_path, monkeypatch):
    TOTPCooldown._instances.clear()
    runtime_state = (
        __import__("pathlib").Path(__file__).resolve().parents[3]
        / "runtime"
        / "dhan-totp-cooldown.json"
    )
    if runtime_state.exists():
        runtime_state.unlink()

    def _for_broker(broker: str, cooldown_seconds: float | None = None):
        return TOTPCooldown(
            broker,
            cooldown_seconds=cooldown_seconds,
            state_path=tmp_path / f"{broker}-totp-cooldown.json",
        )

    monkeypatch.setattr("brokers.adapters.dhan.auth.TOTPCooldown.for_broker", _for_broker)
    yield
    TOTPCooldown._instances.clear()


def _mock_response(json_data, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = str(json_data)
    return resp


def _equity_ref(symbol: str = "RELIANCE", security_id: str = "2885") -> DhanInstrumentRef:
    return DhanInstrumentRef(
        symbol=symbol,
        security_id=security_id,
        exchange_segment="NSE_EQ",
        instrument_type="EQUITY",
        lot_size=1,
    )


def _patch_resolver(gw: DhanGateway, ref: DhanInstrumentRef | None = None):
    ref = ref or _equity_ref()
    gw._resolver.resolve = MagicMock(return_value=ref)  # type: ignore[method-assign]


class TestDhanGatewayProtocol:
    def test_satisfies_broker_gateway(self):
        gw = DhanGateway(access_token="test", client_id="test")
        assert isinstance(gw, BrokerGateway)
        gw.close()


class TestDhanOrders:
    def setup_method(self):
        self.gw = DhanGateway(
            access_token="test-token", client_id="test-client", allow_live_orders=True
        )
        self.mock_resp = MagicMock()

    def teardown_method(self):
        self.gw.close()

    @patch("brokers.infrastructure.http.resilient_client.requests.Session")
    def test_place_order(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session.request.return_value = _mock_response(
            {
                "orderId": "12345",
                "orderStatus": "OPEN",
            }
        )
        mock_session.headers = {}
        mock_session_cls.return_value = mock_session

        gw = DhanGateway(access_token="tok", client_id="cid", allow_live_orders=True)
        _patch_resolver(gw)
        resp = gw.orders.place_order("RELIANCE", "NSE", Side.BUY, 10)
        assert resp.success
        assert resp.order_id == "12345"

        call_args = mock_session.request.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")
        assert payload["securityId"] == "2885"
        assert payload["exchangeSegment"] == "NSE_EQ"
        assert "tradingSymbol" not in payload
        gw.close()

    @patch("brokers.infrastructure.http.resilient_client.requests.Session")
    def test_cancel_order(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session.request.return_value = _mock_response(
            {"status": "success", "message": "cancelled"}
        )
        mock_session.headers = {}
        mock_session_cls.return_value = mock_session

        gw = DhanGateway(access_token="tok", client_id="cid", allow_live_orders=True)
        gw.orders.get_order = MagicMock(return_value=None)  # type: ignore[method-assign]
        resp = gw.orders.cancel_order("12345")
        assert resp.success
        methods = [c[0][0] for c in mock_session.request.call_args_list]
        assert "DELETE" in methods
        gw.close()

    @patch("brokers.infrastructure.http.resilient_client.requests.Session")
    def test_get_orderbook(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session.request.return_value = _mock_response(
            {
                "data": [
                    {
                        "orderId": "1",
                        "tradingSymbol": "RELIANCE",
                        "orderStatus": "OPEN",
                        "transactionType": 1,
                        "quantity": 10,
                        "exchangeSegment": "NSE_EQ",
                    },
                    {
                        "orderId": "2",
                        "tradingSymbol": "TCS",
                        "orderStatus": "FILLED",
                        "transactionType": 2,
                        "quantity": 5,
                        "exchangeSegment": "NSE_EQ",
                    },
                ]
            }
        )
        mock_session.headers = {}
        mock_session_cls.return_value = mock_session

        gw = DhanGateway(access_token="tok", client_id="cid")
        book = gw.orders.get_orderbook()
        assert len(book) == 2
        gw.close()


class TestDhanMarketData:
    @patch("brokers.infrastructure.http.resilient_client.requests.Session")
    def test_ltp(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session.request.return_value = _mock_response(
            {"data": {"2885": {"last_price": 2500.0}}}
        )
        mock_session.headers = {}
        mock_session_cls.return_value = mock_session

        gw = DhanGateway(access_token="tok", client_id="cid")
        _patch_resolver(gw)
        price = gw.market_data.ltp("RELIANCE")
        assert price == Decimal("2500.0")

        call_args = mock_session.request.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")
        assert payload == {"NSE_EQ": [2885]}
        gw.close()

    @patch("brokers.infrastructure.http.resilient_client.requests.Session")
    def test_quote(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session.request.return_value = _mock_response(
            {"data": {"2885": {"last_price": 2500.0, "volume": 100000}}}
        )
        mock_session.headers = {}
        mock_session_cls.return_value = mock_session

        gw = DhanGateway(access_token="tok", client_id="cid")
        _patch_resolver(gw)
        q = gw.market_data.quote("RELIANCE")
        assert q.symbol == "RELIANCE"
        assert q.ltp == Decimal("2500.0")
        gw.close()


class TestDhanPortfolio:
    @patch("brokers.infrastructure.http.resilient_client.requests.Session")
    def test_positions(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session.request.return_value = _mock_response(
            {
                "data": [
                    {
                        "tradingSymbol": "RELIANCE",
                        "exchangeSegment": "NSE_EQ",
                        "netQty": 10,
                        "productType": "INTRADAY",
                    },
                ]
            }
        )
        mock_session.headers = {}
        mock_session_cls.return_value = mock_session

        gw = DhanGateway(access_token="tok", client_id="cid")
        positions = gw.portfolio.positions()
        assert len(positions) == 1
        assert positions[0].symbol == "RELIANCE"
        gw.close()

    @patch("brokers.infrastructure.http.resilient_client.requests.Session")
    def test_funds(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session.request.return_value = _mock_response(
            {"data": [{"availabelBalance": 50000.0, "utilizedMargin": 10000.0}]}
        )
        mock_session.headers = {}
        mock_session_cls.return_value = mock_session

        gw = DhanGateway(access_token="tok", client_id="cid")
        bal = gw.portfolio.funds()
        assert bal.available_cash == Decimal("50000.0")
        gw.close()


class TestDhanAuth:
    def test_is_authenticated(self):
        gw = DhanGateway(access_token="tok", client_id="cid")
        assert gw.auth.is_authenticated()
        assert gw.auth.get_token() == "tok"
        gw.close()

    def test_not_authenticated_without_token(self):
        gw = DhanGateway(access_token="", client_id="cid")
        assert not gw.auth.is_authenticated()
        gw.close()

    @patch("brokers.adapters.dhan.auth.requests.post")
    @patch("pyotp.TOTP")
    def test_totp_token_generation_success(self, mock_totp_cls, mock_post):
        mock_totp = MagicMock()
        mock_totp.now.return_value = "123456"
        mock_totp_cls.return_value = mock_totp

        mock_post.return_value = _mock_response({"data": {"accessToken": "generated-token-123"}})

        gw = DhanGateway(
            access_token=None,
            client_id="cid",
            pin="1122",
            totp_secret="MYSUPERSECRET",
        )
        assert gw.auth.is_authenticated()
        assert gw.auth.get_token() == "generated-token-123"
        gw.close()

    @patch("brokers.adapters.dhan.auth.requests.post")
    @patch("pyotp.TOTP")
    def test_totp_token_generation_failure(self, mock_totp_cls, mock_post):
        mock_totp = MagicMock()
        mock_totp.now.return_value = "123456"
        mock_totp_cls.return_value = mock_totp

        mock_post.return_value = _mock_response({}, status_code=400)

        with pytest.raises(Exception, match="Token generation failed"):
            DhanGateway(
                access_token=None,
                client_id="cid",
                pin="1122",
                totp_secret="MYSUPERSECRET",
            )

    @patch("brokers.adapters.dhan.auth.requests.post")
    @patch("pyotp.TOTP")
    def test_refresh_token_regenerates(self, mock_totp_cls, mock_post):
        mock_totp = MagicMock()
        mock_totp.now.return_value = "123456"
        mock_totp_cls.return_value = mock_totp

        # First call on init, second on refresh
        mock_post.side_effect = [
            _mock_response({"data": {"accessToken": "generated-token-1"}}),
            _mock_response({"data": {"accessToken": "generated-token-2"}}),
        ]

        gw = DhanGateway(
            access_token=None,
            client_id="cid",
            pin="1122",
            totp_secret="MYSUPERSECRET",
        )
        assert gw.auth.get_token() == "generated-token-1"

        token = gw.auth.refresh_token()
        assert token == "generated-token-1"
        assert mock_post.call_count == 1
        assert gw.auth.get_token() == "generated-token-1"
        gw.close()
