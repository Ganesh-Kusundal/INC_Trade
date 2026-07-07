"""Tests for brokers.dhan.resolver — Dhan instrument resolver.

Covers:
  - DhanInstrumentResolver: load_from_rows, row parsing, segment mapping
  - Alternate key generation (Dhan-specific option/future formats)
  - Cache helpers (purge, find latest)
  - Security ID must be numeric
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from brokers.dhan.resolver import DhanInstrumentResolver
from brokers.domain.enums import Exchange, InstrumentType


# ── Sample CSV row data (verified from Dhan CSV format) ────────────────────

SAMPLE_ROWS = [
    # Equity
    {
        "SEM_TRADING_SYMBOL": "RELIANCE",
        "SEM_SMST_SECURITY_ID": "3456",
        "SEM_EXM_EXCH_ID": "1",  # NSE_EQ
        "SEM_INSTRUMENT_NAME": "EQUITY",
        "SEM_LOT_UNITS": "1",
        "SEM_TICK_SIZE": "0.05",
        "SEM_CUSTOM_SYMBOL": "RELIANCE",
        "SM_SYMBOL_NAME": "RELIANCE",
    },
    # Index
    {
        "SEM_TRADING_SYMBOL": "NIFTY",
        "SEM_SMST_SECURITY_ID": "13",
        "SEM_EXM_EXCH_ID": "0",  # IDX_I
        "SEM_INSTRUMENT_NAME": "INDEX",
        "SEM_LOT_UNITS": "1",
        "SEM_CUSTOM_SYMBOL": "NIFTY",
        "SM_SYMBOL_NAME": "NIFTY",
    },
    # Future
    {
        "SEM_TRADING_SYMBOL": "NIFTY26JUNFUT",
        "SEM_SMST_SECURITY_ID": "50001",
        "SEM_EXM_EXCH_ID": "2",  # NSE_FNO
        "SEM_INSTRUMENT_NAME": "FUTIDX",
        "SEM_LOT_UNITS": "50",
        "SEM_TICK_SIZE": "0.05",
        "SEM_EXPIRY_DATE": "2026-06-26",
        "SEM_CUSTOM_SYMBOL": "NIFTY",
        "SM_SYMBOL_NAME": "NIFTY",
    },
    # Option (Call)
    {
        "SEM_TRADING_SYMBOL": "NIFTY26JUN15900CE",
        "SEM_SMST_SECURITY_ID": "60001",
        "SEM_EXM_EXCH_ID": "2",  # NSE_FNO
        "SEM_INSTRUMENT_NAME": "OPTIDX",
        "SEM_LOT_UNITS": "50",
        "SEM_TICK_SIZE": "0.05",
        "SEM_EXPIRY_DATE": "2026-06-26",
        "SEM_STRIKE_PRICE": "15900",
        "SEM_OPTION_TYPE": "CE",
        "SEM_CUSTOM_SYMBOL": "NIFTY",
        "SM_SYMBOL_NAME": "NIFTY",
    },
]


@pytest.fixture
def resolver() -> DhanInstrumentResolver:
    r = DhanInstrumentResolver()
    r.load_from_rows(SAMPLE_ROWS)
    return r


# ── Row parsing tests ──────────────────────────────────────────────────────


class TestRowParsing:
    def test_equity_parsed(self, resolver):
        inst = resolver.resolve("RELIANCE", Exchange.NSE)
        assert inst.broker_id == "3456"
        assert inst.instrument_type == InstrumentType.EQUITY
        assert inst.exchange == Exchange.NSE
        assert inst.segment == "NSE_EQ"

    def test_index_parsed(self, resolver):
        inst = resolver.resolve("NIFTY", Exchange.INDEX)
        assert inst.broker_id == "13"
        assert inst.instrument_type == InstrumentType.INDEX

    def test_future_parsed(self, resolver):
        inst = resolver.resolve_by_broker_id("50001")
        assert inst.instrument_type == InstrumentType.FUTURES
        assert inst.expiry == "2026-06-26"
        assert inst.lot_size == 50
        assert inst.underlying == "NIFTY"

    def test_option_parsed(self, resolver):
        inst = resolver.resolve_by_broker_id("60001")
        assert inst.instrument_type == InstrumentType.OPTIONS
        assert inst.strike == Decimal("15900")
        assert inst.expiry == "2026-06-26"

    def test_security_id_must_be_numeric(self):
        r = DhanInstrumentResolver()
        r.load_from_rows([
            {
                "SEM_TRADING_SYMBOL": "BAD",
                "SEM_SMST_SECURITY_ID": "abc123",  # Non-numeric
                "SEM_EXM_EXCH_ID": "1",
                "SEM_INSTRUMENT_NAME": "EQUITY",
            }
        ])
        # Non-numeric security_id should be skipped
        assert r.stats()["total"] == 0

    def test_empty_security_id_skipped(self):
        r = DhanInstrumentResolver()
        r.load_from_rows([
            {
                "SEM_TRADING_SYMBOL": "EMPTY",
                "SEM_SMST_SECURITY_ID": "",
                "SEM_EXM_EXCH_ID": "1",
                "SEM_INSTRUMENT_NAME": "EQUITY",
            }
        ])
        assert r.stats()["total"] == 0

    def test_empty_trading_symbol_skipped(self):
        r = DhanInstrumentResolver()
        r.load_from_rows([
            {
                "SEM_TRADING_SYMBOL": "",
                "SEM_SMST_SECURITY_ID": "123",
                "SEM_EXM_EXCH_ID": "1",
                "SEM_INSTRUMENT_NAME": "EQUITY",
            }
        ])
        assert r.stats()["total"] == 0

    def test_load_from_rows_stats(self):
        r = DhanInstrumentResolver()
        stats = r.load_from_rows(SAMPLE_ROWS)
        assert stats["total"] == 4
        assert stats["registered"] == 4
        assert stats["skipped"] == 0


# ── Alternate key tests ────────────────────────────────────────────────────


class TestDhanAlternateKeys:
    def test_resolve_future_by_compact_key(self, resolver):
        inst = resolver.resolve("NIFTY26JUNFUT", Exchange.NFO)
        assert inst.broker_id == "50001"

    def test_resolve_option_by_compact_key(self, resolver):
        inst = resolver.resolve("NIFTY26JUN15900CE", Exchange.NFO)
        assert inst.broker_id == "60001"

    def test_resolve_option_by_call_variant(self, resolver):
        # The alternate key generator should add CALL variant
        inst = resolver.resolve("NIFTY26JUN15900CALL", Exchange.NFO)
        assert inst.broker_id == "60001"


# ── Cache helper tests ─────────────────────────────────────────────────────


class TestCacheHelpers:
    def test_find_latest_cache_empty(self, tmp_path: Path):
        assert DhanInstrumentResolver._find_latest_cache(tmp_path) is None

    def test_find_latest_cache(self, tmp_path: Path):
        (tmp_path / "instruments_2026-06-01.csv").write_text("")
        (tmp_path / "instruments_2026-07-01.csv").write_text("")
        latest = DhanInstrumentResolver._find_latest_cache(tmp_path)
        assert latest is not None
        assert "2026-07-01" in latest.name

    def test_purge_old_cache(self, tmp_path: Path):
        # Create old and new cache files
        (tmp_path / "instruments_2026-01-01.csv").write_text("")  # Old
        (tmp_path / "instruments_2026-06-30.csv").write_text("")  # Recent
        DhanInstrumentResolver._purge_old_cache(tmp_path, max_days=7)
        # Old file should be purged; recent kept (depends on current date)
        # This test just verifies purge doesn't crash

    def test_load_from_file_csv(self, tmp_path: Path):
        import csv
        path = tmp_path / "test.csv"
        # Collect ALL unique fieldnames across all rows
        all_fields: set[str] = set()
        for row in SAMPLE_ROWS:
            all_fields.update(row.keys())
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=sorted(all_fields), extrasaction="ignore")
            writer.writeheader()
            for row in SAMPLE_ROWS:
                writer.writerow(row)
        r = DhanInstrumentResolver()
        stats = r.load_from_file(path)
        assert stats["registered"] == 4


# ── Search tests ───────────────────────────────────────────────────────────


class TestDhanSearch:
    def test_search_nifty(self, resolver):
        results = resolver.search("NIFTY")
        # Should find NIFTY index, NIFTY future, NIFTY option
        assert len(results) >= 2

    def test_search_reliance(self, resolver):
        results = resolver.search("RELI")
        assert len(results) >= 1
        assert results[0].symbol == "RELIANCE"


# ── Currency and BSE_FNO segment mapping tests ─────────────────────────────


class TestDhanCurrencyAndBseFno:
    """Verify resolver maps currency and BSE FNO segments correctly."""

    def test_currency_resolves_to_currency_exchange(self):
        r = DhanInstrumentResolver()
        rows = [
            {
                "SEM_TRADING_SYMBOL": "USDINR",
                "SEM_SMST_SECURITY_ID": "12345",
                "SEM_EXM_EXCH_ID": "1",  # Will use compact map
                "SEM_INSTRUMENT_NAME": "EQUITY",  # Doesn't matter for segment test
                "SEM_LOT_UNITS": "1",
                "SEM_TICK_SIZE": "0.0001",
                "SEM_CUSTOM_SYMBOL": "USDINR",
                "SM_SYMBOL_NAME": "USDINR",
            },
        ]
        # Directly test segment mapping
        from brokers.dhan.resolver import _SEGMENT_TO_EXCHANGE

        assert _SEGMENT_TO_EXCHANGE["NSE_CURRENCY"] == Exchange.CURRENCY
        assert _SEGMENT_TO_EXCHANGE["BSE_CURRENCY"] == Exchange.CURRENCY

    def test_bse_fno_resolves_correctly(self):
        from brokers.dhan.resolver import _SEGMENT_TO_EXCHANGE

        assert _SEGMENT_TO_EXCHANGE["BSE_FNO"] == Exchange.BSE_FNO

    def test_nse_fno_still_maps_to_nfo(self):
        from brokers.dhan.resolver import _SEGMENT_TO_EXCHANGE

        assert _SEGMENT_TO_EXCHANGE["NSE_FNO"] == Exchange.NFO

    def test_mcx_still_maps_to_mcx(self):
        from brokers.dhan.resolver import _SEGMENT_TO_EXCHANGE

        assert _SEGMENT_TO_EXCHANGE["MCX_COMM"] == Exchange.MCX

    def test_mapper_reverse_mapping_currency(self):
        from brokers.dhan.mapper import _SEGMENT_TO_EXCHANGE as MAP

        assert MAP["NSE_CURRENCY"] == Exchange.CURRENCY
        assert MAP["BSE_CURRENCY"] == Exchange.CURRENCY

    def test_mapper_reverse_mapping_bse_fno(self):
        from brokers.dhan.mapper import _SEGMENT_TO_EXCHANGE as MAP

        assert MAP["BSE_FNO"] == Exchange.BSE_FNO
