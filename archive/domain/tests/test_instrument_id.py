"""Tests for domain.instrument_id — canonical InstrumentId."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from domain.instrument_id import InstrumentId


class TestInstrumentIdEquity:
    def test_factory(self):
        iid = InstrumentId.equity("NSE", "RELIANCE")
        assert iid.exchange == "NSE"
        assert iid.underlying == "RELIANCE"
        assert iid.expiry is None
        assert iid.strike is None
        assert iid.right is None

    def test_str(self):
        iid = InstrumentId.equity("NSE", "RELIANCE")
        assert str(iid) == "NSE:RELIANCE"

    def test_is_equity(self):
        iid = InstrumentId.equity("NSE", "RELIANCE")
        assert iid.is_equity
        assert not iid.is_index
        assert not iid.is_future
        assert not iid.is_option

    def test_asset_type(self):
        assert InstrumentId.equity("NSE", "RELIANCE").asset_type == "EQUITY"


class TestInstrumentIdIndex:
    def test_factory(self):
        iid = InstrumentId.index("NSE", "NIFTY")
        assert iid.is_index
        assert iid.asset_type == "INDEX"

    def test_str(self):
        iid = InstrumentId.index("NSE", "NIFTY")
        assert str(iid) == "NSE:NIFTY"


class TestInstrumentIdFuture:
    def test_factory(self):
        expiry = date(2026, 7, 30)
        iid = InstrumentId.future("NFO", "NIFTY", expiry)
        assert iid.exchange == "NFO"
        assert iid.underlying == "NIFTY"
        assert iid.expiry == expiry
        assert iid.right == "FUT"
        assert iid.strike is None

    def test_str(self):
        iid = InstrumentId.future("NFO", "NIFTY", date(2026, 7, 30))
        assert str(iid) == "NFO:NIFTY:20260730:FUT"

    def test_is_future(self):
        iid = InstrumentId.future("NFO", "NIFTY", date(2026, 7, 30))
        assert iid.is_future
        assert not iid.is_option
        assert not iid.is_equity


class TestInstrumentIdOption:
    def test_factory_call(self):
        iid = InstrumentId.option("NFO", "NIFTY", date(2026, 7, 30), 25000, "CE")
        assert iid.exchange == "NFO"
        assert iid.underlying == "NIFTY"
        assert iid.expiry == date(2026, 7, 30)
        assert iid.strike == Decimal("25000")
        assert iid.right == "CE"

    def test_str_call(self):
        iid = InstrumentId.option("NFO", "NIFTY", date(2026, 7, 30), 25000, "CE")
        assert str(iid) == "NFO:NIFTY:20260730:25000:CE"

    def test_is_call(self):
        iid = InstrumentId.option("NFO", "NIFTY", date(2026, 7, 30), 25000, "CE")
        assert iid.is_call
        assert not iid.is_put
        assert iid.is_option

    def test_is_put(self):
        iid = InstrumentId.option("NFO", "NIFTY", date(2026, 7, 30), 24000, "PE")
        assert iid.is_put
        assert not iid.is_call

    def test_strike_normalized_from_float(self):
        iid = InstrumentId.option("NFO", "NIFTY", date(2026, 7, 30), 25000.0, "CE")
        assert iid.strike == Decimal("25000")


class TestInstrumentIdParse:
    def test_parse_equity(self):
        iid = InstrumentId.parse("NSE:RELIANCE")
        assert iid.exchange == "NSE"
        assert iid.underlying == "RELIANCE"
        assert iid.expiry is None

    def test_parse_future(self):
        iid = InstrumentId.parse("NFO:NIFTY:20260730:FUT")
        assert iid.expiry == date(2026, 7, 30)
        assert iid.right == "FUT"

    def test_parse_option(self):
        iid = InstrumentId.parse("NFO:NIFTY:20260730:25000:CE")
        assert iid.expiry == date(2026, 7, 30)
        assert iid.strike == Decimal("25000")
        assert iid.right == "CE"

    def test_parse_invalid_raises(self):
        with pytest.raises(ValueError, match="Invalid InstrumentId"):
            InstrumentId.parse("INVALID")

    def test_roundtrip_equity(self):
        original = InstrumentId.equity("NSE", "RELIANCE")
        parsed = InstrumentId.parse(str(original))
        assert parsed == original

    def test_roundtrip_option(self):
        original = InstrumentId.option("NFO", "NIFTY", date(2026, 7, 30), 25000, "CE")
        parsed = InstrumentId.parse(str(original))
        assert parsed == original


class TestInstrumentIdValidation:
    def test_invalid_exchange_raises(self):
        with pytest.raises(ValueError, match="Invalid exchange"):
            InstrumentId(exchange="INVALID", underlying="X")

    def test_invalid_right_raises(self):
        with pytest.raises(ValueError, match="Invalid right"):
            InstrumentId(exchange="NFO", underlying="NIFTY", right="INVALID")


class TestInstrumentIdEquality:
    def test_equal_same_fields(self):
        a = InstrumentId.equity("NSE", "RELIANCE")
        b = InstrumentId.equity("NSE", "RELIANCE")
        assert a == b

    def test_not_equal_different_exchange(self):
        a = InstrumentId.equity("NSE", "RELIANCE")
        b = InstrumentId.equity("BSE", "RELIANCE")
        assert a != b

    def test_hashable_in_set(self):
        a = InstrumentId.equity("NSE", "RELIANCE")
        b = InstrumentId.equity("NSE", "RELIANCE")
        assert len({a, b}) == 1


class TestInstrumentIdConvenience:
    def test_with_expiry(self):
        eq = InstrumentId.equity("NSE", "RELIANCE")
        fut = eq.with_expiry(date(2026, 7, 30))
        assert fut.expiry == date(2026, 7, 30)
        assert fut.underlying == "RELIANCE"

    def test_with_strike(self):
        iid = InstrumentId(exchange="NFO", underlying="NIFTY", expiry=date(2026, 7, 30), right="FUT")
        with_strike = iid.with_strike(25000)
        assert with_strike.strike == Decimal("25000")

    def test_to_equity(self):
        opt = InstrumentId.option("NFO", "NIFTY", date(2026, 7, 30), 25000, "CE")
        eq = opt.to_equity()
        assert eq.exchange == "NFO"
        assert eq.underlying == "NIFTY"
        assert eq.expiry is None
        assert eq.strike is None
        assert eq.right is None

    def test_key_tuple(self):
        iid = InstrumentId.equity("NSE", "RELIANCE")
        assert iid.key == ("NSE", "RELIANCE", None, None, None)
