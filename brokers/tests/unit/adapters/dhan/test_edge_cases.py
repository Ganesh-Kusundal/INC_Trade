"""Edge case tests for Dhan broker adapter."""

from __future__ import annotations

import pytest
from brokers.domain.enums import OrderType, ProductType, Side
from brokers.domain.exceptions import InstrumentNotFoundError

from brokers.adapters.dhan.identity import DhanInstrumentResolver
from brokers.adapters.dhan.orders import DhanOrders

SAMPLE_ROWS = [
    {
        "SEM_TRADING_SYMBOL": "RELIANCE",
        "SEM_SMST_SECURITY_ID": "2885",
        "SEM_EXM_EXCH_ID": "NSE",
        "SEM_INSTRUMENT_NAME": "EQUITY",
        "SEM_LOT_UNITS": "1",
        "SEM_TICK_SIZE": "0.05",
        "SEM_CUSTOM_SYMBOL": "Reliance Industries",
    },
    {
        "SEM_TRADING_SYMBOL": "TCS",
        "SEM_SMST_SECURITY_ID": "11536",
        "SEM_EXM_EXCH_ID": "NSE",
        "SEM_INSTRUMENT_NAME": "EQUITY",
        "SEM_LOT_UNITS": "1",
        "SEM_TICK_SIZE": "10",
        "SEM_CUSTOM_SYMBOL": "Tata Consultancy Services",
    },
    {
        "SEM_TRADING_SYMBOL": "NIFTY 26 JUN FUT",
        "SEM_SMST_SECURITY_ID": "99999",
        "SEM_EXM_EXCH_ID": "NSE",
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
def resolver() -> DhanInstrumentResolver:
    res = DhanInstrumentResolver()

    import csv
    import io

    output = io.StringIO()
    # Collect all keys present in any of the sample rows
    keys_seen = {}
    for row in SAMPLE_ROWS:
        for k in row.keys():
            keys_seen[k] = True
    fieldnames = list(keys_seen.keys())

    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(SAMPLE_ROWS)

    res.load_from_csv_text(output.getvalue())
    return res


@pytest.fixture()
def orders_adapter(resolver: DhanInstrumentResolver) -> DhanOrders:
    client = FakeHttpClient()
    return DhanOrders(client=client, resolver=resolver)  # type: ignore


class TestSymbolResolver:
    """Edge cases for symbol resolution."""

    def test_empty_symbol_raises(self, resolver):
        with pytest.raises(InstrumentNotFoundError):
            resolver.resolve("", "NSE")

    def test_none_like_symbol_raises(self, resolver):
        with pytest.raises(InstrumentNotFoundError):
            resolver.resolve("   ", "NSE")

    def test_case_insensitive(self, resolver):
        inst = resolver.resolve("reliance", "nse")
        assert inst.symbol == "RELIANCE"

    def test_unknown_exchange_raises(self, resolver):
        with pytest.raises(InstrumentNotFoundError):
            resolver.resolve("RELIANCE", "INVALID_EXCHANGE")


class TestOrderValidation:
    """Edge cases for order validation via payload assertions."""

    def test_limit_order_without_price(self, orders_adapter):
        resp = orders_adapter.place_order(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            order_type=OrderType.LIMIT,
            product_type=ProductType.INTRADAY,
        )
        assert not resp.success
        assert resp.error_code == "VALIDATION_FAILED"
