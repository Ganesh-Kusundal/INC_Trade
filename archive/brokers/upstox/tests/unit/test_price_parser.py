from __future__ import annotations

from decimal import Decimal

from brokers.upstox.mappers.price_parser import UpstoxPriceParser


def test_parse_rupee_default():
    p = UpstoxPriceParser.parse(123.45)
    assert p == Decimal("123.4500")


def test_parse_string_rupee():
    p = UpstoxPriceParser.parse("98.765")
    assert p == Decimal("98.7650")


def test_parse_paise_to_rupee():
    p = UpstoxPriceParser.parse(98765, is_paise=True)
    assert p == Decimal("987.6500")


def test_to_paise_from_rupee():
    assert UpstoxPriceParser.to_paise(Decimal("10.50")) == 1050
    assert UpstoxPriceParser.to_paise(10) == 1000
    assert UpstoxPriceParser.to_paise("0.99") == 99


def test_to_rupee_from_paise():
    assert UpstoxPriceParser.to_rupee(1050) == Decimal("10.50")
    assert UpstoxPriceParser.to_rupee(99) == Decimal("0.99")


def test_round_trip_paise():
    for rupee in (Decimal("0.01"), Decimal("1.50"), Decimal("12345.67"), Decimal("99999.99")):
        assert UpstoxPriceParser.to_rupee(UpstoxPriceParser.to_paise(rupee)) == rupee


def test_parse_none_or_empty_returns_zero():
    assert UpstoxPriceParser.parse(None) == Decimal("0.0000")
    assert UpstoxPriceParser.parse("") == Decimal("0.0000")


def test_parse_paise_binary_ws_feed():
    """Binary WS feed sends integer paise — verify conversion."""
    p = UpstoxPriceParser.parse(1234567, is_paise=True)
    assert p == Decimal("12345.6700")


def test_parse_decimal_input_rupees():
    p = UpstoxPriceParser.parse(Decimal("100.05"))
    assert p == Decimal("100.0500")


def test_parse_decimal_input_paise():
    p = UpstoxPriceParser.parse(Decimal("10005"), is_paise=True)
    assert p == Decimal("100.0500")


def test_parse_zero():
    assert UpstoxPriceParser.parse(0) == Decimal("0.0000")
    assert UpstoxPriceParser.parse(0, is_paise=True) == Decimal("0.0000")


def test_to_paise_rounding():
    """Half-up rounding for fractional paise."""
    assert UpstoxPriceParser.to_paise(Decimal("10.505")) == 1051
    assert UpstoxPriceParser.to_paise(Decimal("10.504")) == 1050
