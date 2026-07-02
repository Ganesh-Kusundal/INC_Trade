"""Unit tests for MarketDataAdapter."""

from decimal import Decimal

import pytest

from brokers.dhan.exceptions import InstrumentNotFoundError
from brokers.dhan.market_data import MarketDataAdapter


def test_get_ltp_success(fake_client, resolver):
    fake_client.set_response(
        "POST", "/marketfeed/ltp", {"data": {"NSE_EQ": {"2885": {"last_price": 2450.55}}}}
    )
    adapter = MarketDataAdapter(fake_client, resolver)
    result = adapter.get_ltp("RELIANCE", "NSE")
    assert isinstance(result, Decimal)
    assert result == Decimal("2450.55")


def test_get_ltp_uses_int_security_id(fake_client, resolver):
    fake_client.set_response(
        "POST", "/marketfeed/ltp", {"data": {"NSE_EQ": {"2885": {"last_price": 2450.0}}}}
    )
    adapter = MarketDataAdapter(fake_client, resolver)
    adapter.get_ltp("RELIANCE", "NSE")
    payloads = fake_client.calls_for("POST", "/marketfeed/ltp")
    assert len(payloads) == 1
    payload = payloads[0]
    # The security id in the payload list must be an int, not a string
    assert payload == {"NSE_EQ": [2885]}
    assert isinstance(payload["NSE_EQ"][0], int)


def test_get_ltp_unknown_symbol(fake_client, resolver):
    adapter = MarketDataAdapter(fake_client, resolver)
    with pytest.raises(InstrumentNotFoundError):
        adapter.get_ltp("NONEXISTENT", "NSE")


def test_get_quote_success(fake_client, resolver):
    fake_client.set_response(
        "POST",
        "/marketfeed/quote",
        {
            "data": {
                "NSE_EQ": {
                    "2885": {
                        "last_price": 2450.55,
                        "ohlc": {
                            "open": 2440.0,
                            "high": 2465.0,
                            "low": 2435.0,
                            "close": 2442.0,
                        },
                        "volume": 1234567,
                        "net_change": 8.55,
                    }
                }
            }
        },
    )
    adapter = MarketDataAdapter(fake_client, resolver)
    quote = adapter.get_quote("RELIANCE", "NSE")
    assert quote.symbol == "RELIANCE"
    assert quote.ltp == Decimal("2450.55")
    assert quote.open == Decimal("2440.0")
    assert quote.high == Decimal("2465.0")
    assert quote.low == Decimal("2435.0")
    assert quote.close == Decimal("2442.0")
    assert quote.volume == 1234567
    assert quote.change == Decimal("8.55")


def test_get_depth_success(fake_client, resolver):
    fake_client.set_response(
        "POST",
        "/marketfeed/quote",
        {
            "data": {
                "NSE_EQ": {
                    "2885": {
                        "last_price": 2450.0,
                        "depth": {
                            "buy": [
                                {"price": 2450.0, "quantity": 100, "orders": 5},
                                {"price": 2449.5, "quantity": 200, "orders": 3},
                            ],
                            "sell": [
                                {"price": 2451.0, "quantity": 150, "orders": 4},
                                {"price": 2451.5, "quantity": 250, "orders": 2},
                            ],
                        },
                    }
                }
            }
        },
    )
    adapter = MarketDataAdapter(fake_client, resolver)
    depth = adapter.get_depth("RELIANCE", "NSE")
    assert depth.symbol == "RELIANCE"
    assert len(depth.bids) == 2
    assert len(depth.asks) == 2
    assert depth.bids[0].price == Decimal("2450.0")
    assert depth.bids[0].quantity == 100
    assert depth.bids[0].orders == 5
    assert depth.asks[0].price == Decimal("2451.0")
    assert depth.asks[0].quantity == 150
    assert depth.asks[0].orders == 4
