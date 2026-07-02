"""Integration tests — verify security ID flows correctly through all adapters."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from brokers.adapters.dhan.gateway import DhanGateway
from brokers.domain import Side


SAMPLE_CSV = (
    "SEM_TRADING_SYMBOL,SEM_SMST_SECURITY_ID,SEM_EXM_EXCH_ID,SEM_INSTRUMENT_NAME,"
    "SEM_LOT_UNITS,SEM_OPTION_TYPE,SEM_STRIKE_PRICE,SEM_EXPIRY_DATE,SM_SYMBOL_NAME\n"
    "RELIANCE,2885,NSE,EQUITY,1,,,,RELIANCE\n"
    "NIFTY,13,NSE,INDEX,1,,,,NIFTY\n"
    "NIFTY 26 JUN 25000 CE,55000,NFO,OPTIDX,25,CE,25000,2025-06-26,NIFTY\n"
    "RELIANCE 2800 PE,55002,NFO,OPTSTK,1,PE,2800,2025-06-26,RELIANCE\n"
    "NIFTY 26 JUN FUT,51976,NFO,FUTIDX,25,,,2025-06-26,NIFTY\n"
    "CRUDEOIL 26 JUN FUT,44772,MCX,FUTCOM,100,,,2025-06-26,CRUDEOIL\n"
    "GOLD 60000 CE,44800,MCX,OPTCOM,1,CE,60000,2025-06-26,GOLD\n"
)


def _mock_response(json_data, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = str(json_data)
    return resp


def _make_gateway_with_csv() -> DhanGateway:
    gw = DhanGateway(access_token="tok", client_id="cid")
    gw._resolver.load_from_csv_text(SAMPLE_CSV)
    return gw


def _get_sent_payload(mock_session: MagicMock) -> dict:
    call_args = mock_session.request.call_args
    return call_args.kwargs.get("json") or call_args[1].get("json")


class TestDhanOrdersSecurityId:
    @patch("brokers.adapters.dhan.http.requests.Session")
    def test_place_order_uses_security_id(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session.request.return_value = _mock_response(
            {"orderId": "1", "orderStatus": "OPEN"}
        )
        mock_session.headers = {}
        mock_session_cls.return_value = mock_session

        gw = _make_gateway_with_csv()
        gw.orders.place_order("RELIANCE", "NSE", Side.BUY, 10)

        payload = _get_sent_payload(mock_session)
        assert payload["securityId"] == "2885"
        assert "tradingSymbol" not in payload
        gw.close()

    @patch("brokers.adapters.dhan.http.requests.Session")
    def test_place_order_equity_payload(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session.request.return_value = _mock_response(
            {"orderId": "1", "orderStatus": "OPEN"}
        )
        mock_session.headers = {}
        mock_session_cls.return_value = mock_session

        gw = _make_gateway_with_csv()
        gw.orders.place_order("RELIANCE", "NSE", Side.BUY, 10)

        payload = _get_sent_payload(mock_session)
        assert payload["securityId"] == "2885"
        assert payload["exchangeSegment"] == "NSE_EQ"
        gw.close()

    @patch("brokers.adapters.dhan.http.requests.Session")
    def test_place_order_option_payload(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session.request.return_value = _mock_response(
            {"orderId": "2", "orderStatus": "OPEN"}
        )
        mock_session.headers = {}
        mock_session_cls.return_value = mock_session

        gw = _make_gateway_with_csv()
        gw.orders.place_order("NIFTY 26 JUN 25000 CE", "NFO", Side.BUY, 25)

        payload = _get_sent_payload(mock_session)
        assert payload["securityId"] == "55000"
        assert payload["exchangeSegment"] == "NSE_FNO"
        gw.close()

    @patch("brokers.adapters.dhan.http.requests.Session")
    def test_place_order_mcx_future_payload(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session.request.return_value = _mock_response(
            {"orderId": "3", "orderStatus": "OPEN"}
        )
        mock_session.headers = {}
        mock_session_cls.return_value = mock_session

        gw = _make_gateway_with_csv()
        gw.orders.place_order("CRUDEOIL 26 JUN FUT", "MCX", Side.BUY, 1)

        payload = _get_sent_payload(mock_session)
        assert payload["securityId"] == "44772"
        assert payload["exchangeSegment"] == "MCX_COMM"
        gw.close()


class TestDhanMarketDataSecurityId:
    @patch("brokers.adapters.dhan.http.requests.Session")
    def test_ltp_uses_int_security_id(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session.request.return_value = _mock_response(
            {"data": {"2885": {"last_price": 2500.0}}}
        )
        mock_session.headers = {}
        mock_session_cls.return_value = mock_session

        gw = _make_gateway_with_csv()
        gw.market_data.ltp("RELIANCE")

        payload = _get_sent_payload(mock_session)
        assert payload == {"NSE_EQ": [2885]}
        gw.close()

    @patch("brokers.adapters.dhan.http.requests.Session")
    def test_quote_uses_int_security_id(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session.request.return_value = _mock_response(
            {"data": {"55000": {"last_price": 150.0}}}
        )
        mock_session.headers = {}
        mock_session_cls.return_value = mock_session

        gw = _make_gateway_with_csv()
        gw.market_data.quote("NIFTY 26 JUN 25000 CE", "NFO")

        payload = _get_sent_payload(mock_session)
        assert payload == {"NSE_FNO": [55000]}
        gw.close()

    @patch("brokers.adapters.dhan.http.requests.Session")
    def test_depth_uses_int_security_id(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session.request.return_value = _mock_response({"data": {"44772": {}}})
        mock_session.headers = {}
        mock_session_cls.return_value = mock_session

        gw = _make_gateway_with_csv()
        gw.market_data.depth("CRUDEOIL 26 JUN FUT", "MCX")

        payload = _get_sent_payload(mock_session)
        assert payload == {"MCX_COMM": [44772]}
        gw.close()


class TestDhanHistoricalSecurityId:
    @patch("brokers.adapters.dhan.http.requests.Session")
    def test_candles_uses_security_id(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session.request.return_value = _mock_response(
            {
                "data": [
                    {
                        "timestamp": "2025-01-01",
                        "open": 100,
                        "high": 110,
                        "low": 90,
                        "close": 105,
                        "volume": 1000,
                    }
                ]
            }
        )
        mock_session.headers = {}
        mock_session_cls.return_value = mock_session

        gw = _make_gateway_with_csv()
        gw.historical.get_candles("RELIANCE", "NSE", "2025-01-01", "2025-01-31")

        payload = _get_sent_payload(mock_session)
        assert payload["securityId"] == "2885"
        assert payload["exchangeSegment"] == "NSE_EQ"
        assert payload["instrument"] == "EQUITY"
        gw.close()

    @patch("brokers.adapters.dhan.http.requests.Session")
    def test_candles_equity_instrument(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session.request.return_value = _mock_response({"data": []})
        mock_session.headers = {}
        mock_session_cls.return_value = mock_session

        gw = _make_gateway_with_csv()
        gw.historical.get_candles("RELIANCE", "NSE", "2025-01-01", "2025-01-31")

        payload = _get_sent_payload(mock_session)
        assert payload["instrument"] == "EQUITY"
        gw.close()

    @patch("brokers.adapters.dhan.http.requests.Session")
    def test_candles_option_instrument(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session.request.return_value = _mock_response({"data": []})
        mock_session.headers = {}
        mock_session_cls.return_value = mock_session

        gw = _make_gateway_with_csv()
        gw.historical.get_candles(
            "NIFTY 26 JUN 25000 CE", "NFO", "2025-01-01", "2025-01-31"
        )

        payload = _get_sent_payload(mock_session)
        assert payload["securityId"] == "55000"
        assert payload["instrument"] == "OPTIDX"
        assert payload["exchangeSegment"] == "NSE_FNO"
        gw.close()

    @patch("brokers.adapters.dhan.http.requests.Session")
    def test_candles_future_instrument(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session.request.return_value = _mock_response({"data": []})
        mock_session.headers = {}
        mock_session_cls.return_value = mock_session

        gw = _make_gateway_with_csv()
        gw.historical.get_candles("NIFTY 26 JUN FUT", "NFO", "2025-01-01", "2025-01-31")

        payload = _get_sent_payload(mock_session)
        assert payload["securityId"] == "51976"
        assert payload["instrument"] == "FUTIDX"
        gw.close()

    @patch("brokers.adapters.dhan.http.requests.Session")
    def test_candles_mcx_future_instrument(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session.request.return_value = _mock_response({"data": []})
        mock_session.headers = {}
        mock_session_cls.return_value = mock_session

        gw = _make_gateway_with_csv()
        gw.historical.get_candles(
            "CRUDEOIL 26 JUN FUT", "MCX", "2025-01-01", "2025-01-31"
        )

        payload = _get_sent_payload(mock_session)
        assert payload["securityId"] == "44772"
        assert payload["instrument"] == "FUTCOM"
        assert payload["exchangeSegment"] == "MCX_COMM"
        gw.close()

    @patch("brokers.adapters.dhan.http.requests.Session")
    def test_candles_index_instrument(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session.request.return_value = _mock_response({"data": []})
        mock_session.headers = {}
        mock_session_cls.return_value = mock_session

        gw = _make_gateway_with_csv()
        gw.historical.get_candles("NIFTY", "INDEX", "2025-01-01", "2025-01-31")

        payload = _get_sent_payload(mock_session)
        assert payload["securityId"] == "13"
        assert payload["instrument"] == "EQUITY"
        assert payload["exchangeSegment"] == "IDX_I"
        gw.close()
