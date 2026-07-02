"""Tests for historical data adapters and streaming adapters."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch


from brokers.adapters.dhan.gateway import DhanGateway
from brokers.adapters.dhan.streaming import DhanStreaming
from brokers.adapters.upstox.gateway import UpstoxGateway
from brokers.adapters.upstox.streaming import UpstoxStreaming

_HISTORICAL_CSV = (
    "SEM_TRADING_SYMBOL,SEM_SMST_SECURITY_ID,SEM_EXM_EXCH_ID,SEM_INSTRUMENT_NAME,"
    "SEM_LOT_UNITS,SEM_OPTION_TYPE,SEM_STRIKE_PRICE,SEM_EXPIRY_DATE,SM_SYMBOL_NAME\n"
    "RELIANCE,2885,NSE,EQUITY,1,,,,RELIANCE\n"
)


def _mock_response(json_data, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = str(json_data)
    return resp


def _preload_resolver(gw: DhanGateway) -> None:
    gw._resolver.load_from_csv_text(_HISTORICAL_CSV)


class TestDhanHistorical:
    @patch("brokers.adapters.dhan.http.requests.Session")
    def test_get_candles_daily(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session.request.return_value = _mock_response(
            {
                "data": [
                    {
                        "timestamp": 1700000000,
                        "open": 100,
                        "high": 105,
                        "low": 99,
                        "close": 103,
                        "volume": 5000,
                    },
                    {
                        "timestamp": 1700086400,
                        "open": 103,
                        "high": 108,
                        "low": 102,
                        "close": 107,
                        "volume": 6000,
                    },
                ]
            }
        )
        mock_session.headers = {}
        mock_session_cls.return_value = mock_session

        gw = DhanGateway(access_token="tok", client_id="cid")
        _preload_resolver(gw)
        candles = gw.historical.get_candles(
            "RELIANCE", "NSE", "2024-01-01", "2024-01-31", "1D"
        )
        assert len(candles) == 2
        assert candles[0]["open"] == 100.0
        assert candles[1]["volume"] == 6000
        gw.close()

    @patch("brokers.adapters.dhan.http.requests.Session")
    def test_get_candles_empty(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session.request.return_value = _mock_response({"data": []})
        mock_session.headers = {}
        mock_session_cls.return_value = mock_session

        gw = DhanGateway(access_token="tok", client_id="cid")
        _preload_resolver(gw)
        candles = gw.historical.get_candles(
            "RELIANCE", "NSE", "2024-01-01", "2024-01-31"
        )
        assert candles == []
        gw.close()


class TestUpstoxHistorical:
    @patch("brokers.adapters.upstox.http.requests.Session")
    def test_get_candles_daily(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session.request.return_value = _mock_response(
            {
                "data": {
                    "candles": [
                        ["2024-01-01T00:00:00+0530", 100.0, 105.0, 99.0, 103.0, 5000],
                        ["2024-01-02T00:00:00+0530", 103.0, 108.0, 102.0, 107.0, 6000],
                    ]
                }
            }
        )
        mock_session.headers = {}
        mock_session_cls.return_value = mock_session

        gw = UpstoxGateway(access_token="tok")
        candles = gw.historical.get_candles(
            "RELIANCE", "NSE", "2024-01-01", "2024-01-31", "1D"
        )
        assert len(candles) == 2
        assert candles[0]["open"] == 100.0
        assert candles[0]["close"] == 103.0
        assert candles[1]["volume"] == 6000
        gw.close()

    @patch("brokers.adapters.upstox.http.requests.Session")
    def test_get_candles_empty(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session.request.return_value = _mock_response({"data": {"candles": []}})
        mock_session.headers = {}
        mock_session_cls.return_value = mock_session

        gw = UpstoxGateway(access_token="tok")
        candles = gw.historical.get_candles(
            "RELIANCE", "NSE", "2024-01-01", "2024-01-31"
        )
        assert candles == []
        gw.close()


class TestDhanStreaming:
    def test_subscribe_tracks_keys(self):
        s = DhanStreaming(access_token="tok", client_id="cid")
        s.subscribe("RELIANCE", "NSE")
        assert "NSE_EQ|RELIANCE" in s._subscriptions

    def test_unsubscribe_removes_key(self):
        s = DhanStreaming(access_token="tok", client_id="cid")
        s.subscribe("RELIANCE", "NSE")
        s.unsubscribe("RELIANCE", "NSE")
        assert "NSE_EQ|RELIANCE" not in s._subscriptions

    def test_on_tick_callback(self):
        s = DhanStreaming(access_token="tok", client_id="cid")
        ticks = []
        s.on_tick = lambda t: ticks.append(t)
        assert s.on_tick is not None

    def test_is_connected_false_initially(self):
        s = DhanStreaming(access_token="tok", client_id="cid")
        assert not s.is_connected

    def test_parse_tick(self):
        tick = DhanStreaming._parse_tick(
            {
                "symbol": "RELIANCE",
                "exchange": "NSE",
                "lastPrice": 2500.50,
                "volume": 100000,
            }
        )
        assert tick is not None
        assert tick["symbol"] == "RELIANCE"
        assert tick["ltp"] == Decimal("2500.50")
        assert tick["volume"] == 100000

    def test_parse_tick_none_for_invalid(self):
        assert DhanStreaming._parse_tick(None) is None
        assert DhanStreaming._parse_tick("not a dict") is None


class TestUpstoxStreaming:
    def test_subscribe_tracks_keys(self):
        s = UpstoxStreaming(access_token="tok")
        s.subscribe("RELIANCE", "NSE")
        assert "NSE_EQ|RELIANCE" in s._subscriptions

    def test_unsubscribe_removes_key(self):
        s = UpstoxStreaming(access_token="tok")
        s.subscribe("RELIANCE", "NSE")
        s.unsubscribe("RELIANCE", "NSE")
        assert "NSE_EQ|RELIANCE" not in s._subscriptions

    def test_on_tick_callback(self):
        s = UpstoxStreaming(access_token="tok")
        ticks = []
        s.on_tick = lambda t: ticks.append(t)
        assert s.on_tick is not None

    def test_is_connected_false_initially(self):
        s = UpstoxStreaming(access_token="tok")
        assert not s.is_connected

    def test_parse_tick(self):
        tick = UpstoxStreaming._parse_tick(
            {
                "symbol": "RELIANCE",
                "exchange": "NSE",
                "last_price": 2500.50,
                "volume": 100000,
            }
        )
        assert tick is not None
        assert tick["symbol"] == "RELIANCE"
        assert tick["ltp"] == Decimal("2500.50")

    def test_fno_subscribe(self):
        s = UpstoxStreaming(access_token="tok")
        s.subscribe("NIFTY 24000 CE", "NFO")
        assert "NSE_FO|NIFTY 24000 CE" in s._subscriptions


class TestGatewayStreamingProperty:
    def test_dhan_has_streaming(self):
        gw = DhanGateway(access_token="tok", client_id="cid")
        assert hasattr(gw, "streaming")
        assert isinstance(gw.streaming, DhanStreaming)
        gw.close()

    def test_upstox_has_streaming(self):
        gw = UpstoxGateway(access_token="tok")
        assert hasattr(gw, "streaming")
        assert isinstance(gw.streaming, UpstoxStreaming)
        gw.close()

    def test_dhan_has_historical(self):
        gw = DhanGateway(access_token="tok", client_id="cid")
        assert hasattr(gw, "historical")
        gw.close()

    def test_upstox_has_historical(self):
        gw = UpstoxGateway(access_token="tok")
        assert hasattr(gw, "historical")
        gw.close()
