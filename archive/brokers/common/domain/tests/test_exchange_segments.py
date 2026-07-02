"""Typed exchange-segment helper tests."""

from __future__ import annotations

import pytest

from domain.exchange_segments import (
    canonical_exchange_short,
    is_commodity_segment,
    is_currency_segment,
    is_derivative_segment,
    is_equity_segment,
    parse_segment,
    wire_value,
)
from domain.types import ExchangeSegment


class TestParseSegment:
    def test_canonical_wire_format(self):
        assert parse_segment("NSE_EQ") is ExchangeSegment.NSE
        assert parse_segment("MCXCOMM") is ExchangeSegment.MCX
        assert parse_segment("NSE_FNO") is ExchangeSegment.NSE_FNO

    def test_mcx_comm_alias(self):
        assert parse_segment("MCX_COMM") is ExchangeSegment.MCX

    def test_mcx_comm_wire_differs_from_enum_value(self):
        assert wire_value("MCX_COMM") == "MCXCOMM"

    @pytest.mark.parametrize(
        ("alias", "expected"),
        [
            ("NSE", ExchangeSegment.NSE),
            ("NSE_EQ", ExchangeSegment.NSE),
            ("BSE", ExchangeSegment.BSE),
            ("BSE_EQ", ExchangeSegment.BSE),
            ("NFO", ExchangeSegment.NSE_FNO),
            ("NSE_FNO", ExchangeSegment.NSE_FNO),
            ("BFO", ExchangeSegment.BSE_FNO),
            ("BSE_FNO", ExchangeSegment.BSE_FNO),
            ("MCX", ExchangeSegment.MCX),
            ("MCXCOMM", ExchangeSegment.MCX),
            ("MCX_COMM", ExchangeSegment.MCX),
            ("CDS", ExchangeSegment.NSE_CURRENCY),
            ("NSE_CURRENCY", ExchangeSegment.NSE_CURRENCY),
            ("BCD", ExchangeSegment.BSE_CURRENCY),
            ("BSE_CURRENCY", ExchangeSegment.BSE_CURRENCY),
            ("IDX_I", ExchangeSegment.IDX_I),
            ("INDEX", ExchangeSegment.IDX_I),
        ],
    )
    def test_alias_permutations(self, alias, expected):
        assert parse_segment(alias) is expected
        assert wire_value(alias) == expected.value

    def test_short_aliases(self):
        assert parse_segment("NSE") is ExchangeSegment.NSE
        assert parse_segment("BSE") is ExchangeSegment.BSE
        assert parse_segment("MCX") is ExchangeSegment.MCX
        assert parse_segment("NFO") is ExchangeSegment.NSE_FNO
        assert parse_segment("CDS") is ExchangeSegment.NSE_CURRENCY

    def test_case_insensitive(self):
        assert parse_segment("nse") is ExchangeSegment.NSE
        assert parse_segment("Mcx") is ExchangeSegment.MCX

    def test_enum_passthrough(self):
        assert parse_segment(ExchangeSegment.MCX) is ExchangeSegment.MCX

    def test_unknown_returns_none_by_default(self):
        assert parse_segment("UNKNOWN") is None

    def test_unknown_returns_default(self):
        assert parse_segment("UNKNOWN", default=ExchangeSegment.NSE) is ExchangeSegment.NSE

    def test_non_string_non_enum_returns_default(self):
        assert parse_segment(12345, default=ExchangeSegment.NSE) is ExchangeSegment.NSE
        assert parse_segment(None, default=ExchangeSegment.NSE) is ExchangeSegment.NSE


class TestIsEquitySegment:
    @pytest.mark.parametrize("seg", ["NSE", "NSE_EQ", "BSE", "BSE_EQ", ExchangeSegment.NSE])
    def test_true(self, seg):
        assert is_equity_segment(seg) is True

    @pytest.mark.parametrize("seg", ["NSE_FNO", "MCX", "NSE_CURRENCY", "BSE_CURRENCY", "BOGUS"])
    def test_false(self, seg):
        assert is_equity_segment(seg) is False


class TestIsDerivativeSegment:
    @pytest.mark.parametrize(
        "seg", ["NSE_FNO", "BSE_FNO", "MCX", "MCXCOMM", "NSE_CURRENCY", "BSE_CURRENCY"]
    )
    def test_true(self, seg):
        assert is_derivative_segment(seg) is True

    @pytest.mark.parametrize("seg", ["NSE", "BSE", "NSE_EQ", "BOGUS"])
    def test_false(self, seg):
        assert is_derivative_segment(seg) is False


class TestIsCurrencySegment:
    @pytest.mark.parametrize("seg", ["NSE_CURRENCY", "CDS", "BSE_CURRENCY", "BCD"])
    def test_true(self, seg):
        assert is_currency_segment(seg) is True

    @pytest.mark.parametrize("seg", ["NSE", "MCX", "BOGUS"])
    def test_false(self, seg):
        assert is_currency_segment(seg) is False


class TestIsCommoditySegment:
    @pytest.mark.parametrize("seg", ["MCX", "MCXCOMM", ExchangeSegment.MCX])
    def test_true(self, seg):
        assert is_commodity_segment(seg) is True

    def test_false(self):
        assert is_commodity_segment("NSE") is False


class TestWireValue:
    def test_known_segment(self):
        assert wire_value("NSE") == "NSE_EQ"
        assert wire_value("MCX") == "MCXCOMM"
        assert wire_value(ExchangeSegment.MCX) == "MCXCOMM"

    def test_unknown_segment_raises(self):
        with pytest.raises(ValueError):
            wire_value("BOGUS")


class TestCanonicalExchangeShort:
    def test_nse_and_nfo(self):
        assert canonical_exchange_short("NSE_EQ") == "NSE"
        assert canonical_exchange_short("NFO") == "NFO"
        assert canonical_exchange_short(ExchangeSegment.MCX) == "MCX"
