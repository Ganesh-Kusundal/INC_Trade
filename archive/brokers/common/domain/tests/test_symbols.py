"""Tests for domain.symbols — centralized symbol normalization.

Covers:
- normalize_symbol: whitespace, case, empty, special chars
- normalize_exchange: whitespace, case, empty
- make_position_key: format, normalization, edge cases
- make_instrument_key: tuple format, normalization
"""

from __future__ import annotations

from domain.symbols import (
    make_instrument_key,
    make_position_key,
    normalize_exchange,
    normalize_symbol,
)


class TestNormalizeSymbol:
    def test_uppercase(self):
        assert normalize_symbol("RELIANCE") == "RELIANCE"

    def test_lowercase(self):
        assert normalize_symbol("reliance") == "RELIANCE"

    def test_mixed_case(self):
        assert normalize_symbol("ReLiAnCe") == "RELIANCE"

    def test_whitespace_stripped(self):
        assert normalize_symbol("  RELIANCE  ") == "RELIANCE"

    def test_tabs_and_newlines(self):
        assert normalize_symbol("\tRELIANCE\n") == "RELIANCE"

    def test_empty_string(self):
        assert normalize_symbol("") == ""

    def test_whitespace_only(self):
        assert normalize_symbol("   ") == ""

    def test_already_normalized(self):
        assert normalize_symbol("RELIANCE") == "RELIANCE"

    def test_with_numbers(self):
        assert normalize_symbol("NIFTY50") == "NIFTY50"

    def test_special_characters(self):
        assert normalize_symbol("NIFTY 50") == "NIFTY 50"

    def test_hyphenated(self):
        assert normalize_symbol("RELIANCE-EQ") == "RELIANCE-EQ"

    def test_single_char(self):
        assert normalize_symbol("a") == "A"

    def test_unicode_whitespace(self):
        # Non-breaking space and other unicode whitespace
        assert normalize_symbol("\u00a0RELIANCE\u00a0") == "RELIANCE"


class TestNormalizeExchange:
    def test_uppercase(self):
        assert normalize_exchange("NSE") == "NSE"

    def test_lowercase(self):
        assert normalize_exchange("nse") == "NSE"

    def test_whitespace(self):
        assert normalize_exchange("  NFO  ") == "NFO"

    def test_empty(self):
        assert normalize_exchange("") == ""

    def test_whitespace_only(self):
        assert normalize_exchange("   ") == ""

    def test_already_normalized(self):
        assert normalize_exchange("NSE") == "NSE"

    def test_mixed_case(self):
        assert normalize_exchange("nSe") == "NSE"


class TestMakePositionKey:
    def test_basic(self):
        assert make_position_key("RELIANCE", "NSE") == "RELIANCE:NSE"

    def test_normalizes_symbol(self):
        assert make_position_key("reliance", "NSE") == "RELIANCE:NSE"

    def test_normalizes_exchange(self):
        assert make_position_key("RELIANCE", "nse") == "RELIANCE:NSE"

    def test_both_normalized(self):
        assert make_position_key("reliance", "nfo") == "RELIANCE:NFO"

    def test_whitespace_stripped(self):
        assert make_position_key("  RELIANCE  ", "  NSE  ") == "RELIANCE:NSE"

    def test_different_exchanges(self):
        assert make_position_key("NIFTY", "NSE") == "NIFTY:NSE"
        assert make_position_key("NIFTY", "NFO") == "NIFTY:NFO"
        assert make_position_key("NIFTY", "IDX_I") == "NIFTY:IDX_I"


class TestMakeInstrumentKey:
    def test_basic(self):
        assert make_instrument_key("RELIANCE", "NSE") == ("RELIANCE", "NSE")

    def test_normalizes(self):
        assert make_instrument_key("reliance", "nse") == ("RELIANCE", "NSE")

    def test_whitespace(self):
        assert make_instrument_key("  RELIANCE  ", "  NSE  ") == ("RELIANCE", "NSE")

    def test_returns_tuple(self):
        result = make_instrument_key("RELIANCE", "NSE")
        assert isinstance(result, tuple)
        assert len(result) == 2
