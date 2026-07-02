"""Edge case tests for Dhan broker adapter."""

from __future__ import annotations

import pytest

from brokers.dhan.connection import DhanConnection
from brokers.dhan.exceptions import InstrumentNotFoundError
from brokers.dhan.gateway import BrokerGateway
from domain import OrderStatus

SAMPLE_ROWS = [
    {
        "SEM_TRADING_SYMBOL": "RELIANCE",
        "SEM_SMST_SECURITY_ID": "2885",
        "SEM_EXM_EXCH_ID": "NSE_EQ",
        "SEM_INSTRUMENT_NAME": "EQUITY",
        "SEM_LOT_UNITS": "1",
        "SEM_TICK_SIZE": "0.05",
        "SEM_CUSTOM_SYMBOL": "Reliance Industries",
    },
    {
        "SEM_TRADING_SYMBOL": "TCS",
        "SEM_SMST_SECURITY_ID": "11536",
        "SEM_EXM_EXCH_ID": "NSE_EQ",
        "SEM_INSTRUMENT_NAME": "EQUITY",
        "SEM_LOT_UNITS": "1",
        "SEM_TICK_SIZE": "10",
        "SEM_CUSTOM_SYMBOL": "Tata Consultancy Services",
    },
    {
        "SEM_TRADING_SYMBOL": "NIFTY 26 JUN FUT",
        "SEM_SMST_SECURITY_ID": "99999",
        "SEM_EXM_EXCH_ID": "NSE_FNO",
        "SEM_INSTRUMENT_NAME": "FUTIDX",
        "SEM_LOT_UNITS": "75",
        "SEM_TICK_SIZE": "0.05",
        "SEM_EXPIRY_DATE": "2026-06-26",
        "SEM_OPTION_TYPE": "",
        "SEM_STRIKE_PRICE": None,
        "SEM_CUSTOM_SYMBOL": "NIFTY 26 JUN FUT",
    },
]


class FakeHttpClient:
    def __init__(self):
        self.client_id = "test"
        self.access_token = "test"

    def get(self, endpoint, **kw):
        return {"data": []}

    def post(self, endpoint, json=None):
        return {"data": []}

    def put(self, endpoint, json=None):
        return {"data": {}}

    def delete(self, endpoint):
        return {"data": {}}


@pytest.fixture()
def offline_gateway() -> BrokerGateway:
    client = FakeHttpClient()
    conn = DhanConnection(client=client)
    conn.instruments.load_from_rows(SAMPLE_ROWS)
    return BrokerGateway(conn)


class TestOrderStatusNormalization:
    """Edge cases for OrderStatus.normalize()."""

    def test_empty_string(self):
        assert OrderStatus.normalize("") == OrderStatus.UNKNOWN

    def test_whitespace(self):
        assert OrderStatus.normalize("  OPEN  ") == OrderStatus.OPEN

    def test_case_insensitive(self):
        assert OrderStatus.normalize("filled") == OrderStatus.FILLED
        assert OrderStatus.normalize("FILLED") == OrderStatus.FILLED

    def test_unknown_status_returns_unknown(self):
        assert OrderStatus.normalize("UNKNOWN_STATUS") == OrderStatus.UNKNOWN

    def test_all_canonical_roundtrip(self):
        for status in OrderStatus:
            assert OrderStatus.normalize(status.value) == status


class TestSymbolResolver:
    """Edge cases for symbol resolution."""

    def test_empty_symbol_raises(self, offline_gateway):
        with pytest.raises(InstrumentNotFoundError):
            offline_gateway.extended.instruments.resolve("", "NSE")

    def test_none_like_symbol_raises(self, offline_gateway):
        with pytest.raises(InstrumentNotFoundError):
            offline_gateway.extended.instruments.resolve("   ", "NSE")

    def test_case_insensitive(self, offline_gateway):
        inst = offline_gateway.extended.instruments.resolve("reliance", "nse")
        assert inst.symbol == "RELIANCE"

    def test_unknown_exchange_raises(self, offline_gateway):
        with pytest.raises(InstrumentNotFoundError):
            offline_gateway.extended.instruments.resolve("RELIANCE", "INVALID_EXCHANGE")


class TestOrderValidation:
    """Edge cases for order validation."""

    def test_zero_quantity(self, offline_gateway):
        errors = offline_gateway.extended.validate_order(
            symbol="RELIANCE",
            exchange="NSE",
            quantity=0,
            order_type="MARKET",
            product_type="INTRADAY",
        )
        assert len(errors) > 0
        assert any("quantity" in e.lower() for e in errors)

    def test_negative_quantity(self, offline_gateway):
        errors = offline_gateway.extended.validate_order(
            symbol="RELIANCE",
            exchange="NSE",
            quantity=-10,
            order_type="MARKET",
            product_type="INTRADAY",
        )
        assert len(errors) > 0

    def test_limit_order_without_price(self, offline_gateway):
        errors = offline_gateway.extended.validate_order(
            symbol="RELIANCE",
            exchange="NSE",
            quantity=10,
            order_type="LIMIT",
            product_type="INTRADAY",
        )
        assert len(errors) > 0
        assert any("price" in e.lower() for e in errors)

    def test_cnc_on_fno_rejected(self, offline_gateway):
        errors = offline_gateway.extended.validate_order(
            symbol="NIFTY 26 JUN FUT",
            exchange="NFO",
            quantity=75,
            order_type="MARKET",
            product_type="CNC",
        )
        assert len(errors) > 0
        assert any("cnc" in e.lower() or "product" in e.lower() for e in errors)


class TestGatewayShortcuts:
    """Edge cases for Gateway convenience methods."""

    def test_history_empty_result(self, offline_gateway):
        df = offline_gateway.history("NONEXISTENT", exchange="NSE")
        assert len(df) == 0

    def test_option_chain_no_expiries(self, offline_gateway):
        """Option chain for non-existent symbol should raise InstrumentNotFoundError."""
        with pytest.raises(InstrumentNotFoundError):
            offline_gateway.option_chain("NONEXISTENT", exchange="NFO")

    def test_describe(self, offline_gateway):
        """describe() should return broker info dict."""
        info = offline_gateway.describe()
        assert "broker" in info
        assert "instruments_loaded" in info

    def test_search(self, offline_gateway):
        """search() should return matching instruments."""
        results = offline_gateway.search("RELIANCE")
        assert len(results) > 0
        assert any(r["symbol"] == "RELIANCE" for r in results)

    def test_search_no_results(self, offline_gateway):
        """search() with no matches should return empty list."""
        results = offline_gateway.search("ZZZZNONEXISTENT")
        assert results == []

    def test_depth_20_validation_index(self, offline_gateway):
        # We need NIFTY to be resolved to verify the fallback or rest API call.
        offline_gateway.extended.instruments.load_from_rows(
            [
                {
                    "SEM_TRADING_SYMBOL": "NIFTY",
                    "SEM_SMST_SECURITY_ID": "13",
                    "SEM_EXM_EXCH_ID": "IDX_I",
                    "SEM_INSTRUMENT_NAME": "INDEX",
                    "SEM_LOT_UNITS": 1,
                    "SEM_TICK_SIZE": 0.05,
                }
            ]
        )

        import unittest.mock as mock

        with mock.patch.object(offline_gateway._conn.market_data, "get_depth") as mock_get_depth:
            offline_gateway.depth_20("NIFTY", "IDX_I")
            mock_get_depth.assert_called_once_with("NIFTY", "IDX_I")

    def test_depth_200_validation_index(self, offline_gateway):
        offline_gateway.extended.instruments.load_from_rows(
            [
                {
                    "SEM_TRADING_SYMBOL": "NIFTY",
                    "SEM_SMST_SECURITY_ID": "13",
                    "SEM_EXM_EXCH_ID": "IDX_I",
                    "SEM_INSTRUMENT_NAME": "INDEX",
                    "SEM_LOT_UNITS": 1,
                    "SEM_TICK_SIZE": 0.05,
                }
            ]
        )

        import unittest.mock as mock

        with mock.patch.object(offline_gateway._conn.market_data, "get_depth") as mock_get_depth:
            offline_gateway.depth_200("NIFTY", "IDX_I")
            mock_get_depth.assert_called_once_with("NIFTY", "IDX_I")
