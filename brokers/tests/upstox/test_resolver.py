"""Tests for brokers.upstox.resolver — Upstox instrument resolver.

Covers:
  - UpstoxInstrumentResolver: load_from_rows, JSON row parsing
  - Instrument key format: "SEGMENT|IDENTIFIER"
  - Segment mapping to Exchange enum
  - ISIN as alternate key
  - Search functionality
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from brokers.upstox.resolver import UpstoxInstrumentResolver
from brokers.domain.enums import Exchange, InstrumentType


# ── Sample JSON rows (verified from Upstox complete.json format) ───────────

SAMPLE_ROWS = [
    # Equity
    {
        "instrument_key": "NSE_EQ|INE002A01018",
        "trading_symbol": "RELIANCE",
        "name": "RELIANCE",
        "instrument_type": "EQUITY",
        "exchange_segment": "NSE_EQ",
        "lot_size": 1,
        "tick_size": 0.05,
        "isin": "INE002A01018",
    },
    # Index
    {
        "instrument_key": "NSE_INDEX|Nifty 50",
        "trading_symbol": "NIFTY 50",
        "name": "NIFTY",
        "instrument_type": "INDEX",
        "segment": "NSE_INDEX",
        "lot_size": 1,
    },
    # Future
    {
        "instrument_key": "NSE_FO|NIFTY26JUNFUT",
        "trading_symbol": "NIFTY26JUNFUT",
        "name": "NIFTY",
        "instrument_type": "FUTURE",
        "segment": "NSE_FO",
        "lot_size": 50,
        "expiry": "2026-06-26",
        "underlying_symbol": "NIFTY",
    },
    # Option (Call)
    {
        "instrument_key": "NSE_FO|NIFTY26JUN15900CE",
        "trading_symbol": "NIFTY26JUN15900CE",
        "name": "NIFTY",
        "instrument_type": "OPTION",
        "segment": "NSE_FO",
        "lot_size": 50,
        "expiry": "2026-06-26",
        "strike_price": 15900,
        "underlying_symbol": "NIFTY",
    },
]


@pytest.fixture
def resolver() -> UpstoxInstrumentResolver:
    r = UpstoxInstrumentResolver()
    r.load_from_rows(SAMPLE_ROWS)
    return r


# ── Row parsing tests ──────────────────────────────────────────────────────


class TestRowParsing:
    def test_equity_parsed(self, resolver):
        inst = resolver.resolve("RELIANCE", Exchange.NSE)
        assert inst.broker_id == "NSE_EQ|INE002A01018"
        assert inst.instrument_type == InstrumentType.EQUITY
        assert inst.exchange == Exchange.NSE
        assert inst.segment == "NSE_EQ"
        assert inst.isin == "INE002A01018"

    def test_index_parsed(self, resolver):
        inst = resolver.resolve("NIFTY", Exchange.INDEX)
        assert inst.instrument_type == InstrumentType.INDEX
        assert inst.segment == "NSE_INDEX"

    def test_future_parsed(self, resolver):
        inst = resolver.resolve_by_broker_id("NSE_FO|NIFTY26JUNFUT")
        assert inst.instrument_type == InstrumentType.FUTURES
        assert inst.expiry == "2026-06-26"
        assert inst.lot_size == 50
        assert inst.underlying == "NIFTY"

    def test_option_parsed(self, resolver):
        inst = resolver.resolve_by_broker_id("NSE_FO|NIFTY26JUN15900CE")
        assert inst.instrument_type == InstrumentType.OPTIONS
        assert inst.strike == Decimal("15900")
        assert inst.expiry == "2026-06-26"

    def test_empty_instrument_key_skipped(self):
        r = UpstoxInstrumentResolver()
        r.load_from_rows([{"instrument_key": "", "trading_symbol": "X", "name": "X"}])
        assert r.stats()["total"] == 0

    def test_stats(self, resolver):
        stats = resolver.stats()
        assert stats["total"] == 4

    def test_load_from_rows_stats(self):
        r = UpstoxInstrumentResolver()
        stats = r.load_from_rows(SAMPLE_ROWS)
        assert stats["total"] == 4
        assert stats["registered"] == 4
        assert stats["skipped"] == 0


# ── Alternate key tests ────────────────────────────────────────────────────


class TestUpstoxAlternateKeys:
    def test_resolve_by_isin(self, resolver):
        inst = resolver.resolve_by_broker_id("INE002A01018")
        assert inst.broker_id == "NSE_EQ|INE002A01018"

    def test_resolve_by_identifier_portion(self, resolver):
        # The identifier portion "INE002A01018" should be an alternate key
        inst = resolver.resolve_by_broker_id("INE002A01018")
        assert inst.symbol == "RELIANCE"

    def test_resolve_option_by_compact_key(self, resolver):
        inst = resolver.resolve("NIFTY26JUN15900CE", Exchange.NFO)
        assert inst.broker_id == "NSE_FO|NIFTY26JUN15900CE"

    def test_resolve_future_by_compact_key(self, resolver):
        inst = resolver.resolve("NIFTY26JUNFUT", Exchange.NFO)
        assert inst.broker_id == "NSE_FO|NIFTY26JUNFUT"


# ── JSON key variation tests ────────────────────────────────────────────────


class TestKeyVariations:
    def test_tradingSymbol_camelCase(self):
        r = UpstoxInstrumentResolver()
        r.load_from_rows([{
            "instrument_key": "NSE_EQ|INE123",
            "tradingSymbol": "TCS",
            "name": "TCS",
            "instrument_type": "EQUITY",
            "exchange_segment": "NSE_EQ",
            "lotSize": 1,
            "tickSize": 0.05,
            "isin": "INE123",
        }])
        inst = r.resolve("TCS", Exchange.NSE)
        assert inst.broker_id == "NSE_EQ|INE123"
        assert inst.trading_symbol == "TCS"

    def test_strike_price_camelCase(self):
        r = UpstoxInstrumentResolver()
        r.load_from_rows([{
            "instrument_key": "NSE_FO|TEST26JUN100CE",
            "trading_symbol": "TEST26JUN100CE",
            "name": "TEST",
            "instrument_type": "OPTION",
            "segment": "NSE_FO",
            "lot_size": 1,
            "expiry": "2026-06-26",
            "strikePrice": 100,
            "underlying_symbol": "TEST",
        }])
        inst = r.resolve_by_broker_id("NSE_FO|TEST26JUN100CE")
        assert inst.strike == Decimal("100")


# ── Search tests ───────────────────────────────────────────────────────────


class TestUpstoxSearch:
    def test_search_nifty(self, resolver):
        results = resolver.search("NIFTY")
        assert len(results) >= 2

    def test_search_reliance(self, resolver):
        results = resolver.search("RELI")
        assert len(results) >= 1
        assert results[0].symbol == "RELIANCE"
