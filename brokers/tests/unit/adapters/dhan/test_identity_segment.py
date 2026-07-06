"""Unit tests for Dhan identity expected_segment guard."""

from __future__ import annotations

import pytest
from inc_trade.domain.exceptions import InstrumentNotFoundError

from brokers.adapters.dhan.identity import DhanInstrumentResolver


def _load_resolver() -> DhanInstrumentResolver:
    csv = (
        "SEM_TRADING_SYMBOL,SEM_SMST_SECURITY_ID,SEM_EXM_EXCH_ID,SEM_INSTRUMENT_NAME,SEM_LOT_UNITS\n"
        "RELIANCE,2885,NSE,EQUITY,1.0\n"
        "NIFTY,99926000,NSE,INDEX,1.0\n"
        "NIFTY24JUL25000CE,35000,NSE,OPTIDX,50.0\n"
    )
    resolver = DhanInstrumentResolver()
    resolver.load_from_csv_text(csv)
    return resolver


class TestExpectedSegment:
    def test_derivative_requires_matching_segment(self):
        resolver = _load_resolver()
        ref = resolver.resolve(
            "NIFTY24JUL25000CE", "NFO", expected_segment="NSE_FNO"
        )
        assert ref.exchange_segment == "NSE_FNO"

    def test_wrong_expected_segment_raises(self):
        resolver = _load_resolver()
        with pytest.raises(InstrumentNotFoundError, match="required"):
            resolver.resolve(
                "NIFTY24JUL25000CE", "NFO", expected_segment="NSE_EQ"
            )

    def test_explicit_segment_match(self):
        resolver = _load_resolver()
        ref = resolver.resolve("RELIANCE", "NSE", expected_segment="NSE_EQ")
        assert ref.exchange_segment == "NSE_EQ"


class TestSymbolNormalizationParity:
    def test_index_on_nse_exchange_fallback(self):
        resolver = _load_resolver()
        ref = resolver.resolve("NIFTY", "NSE")
        assert ref.security_id == "99926000"
        assert ref.exchange_segment == "IDX_I"

    def test_call_suffix_maps_to_ce(self):
        csv = (
            "SEM_TRADING_SYMBOL,SEM_SMST_SECURITY_ID,SEM_EXM_EXCH_ID,SEM_INSTRUMENT_NAME,SEM_LOT_UNITS\n"
            "NIFTY 26 JUN 25000 CE,55000,NSE,OPTIDX,50.0\n"
        )
        resolver = DhanInstrumentResolver()
        resolver.load_from_csv_text(csv)
        ref = resolver.resolve("NIFTY 26 JUN 25000 CALL", "NFO")
        assert ref.security_id == "55000"

    def test_hardcoded_index_without_csv_row(self):
        resolver = DhanInstrumentResolver()
        resolver.load_from_csv_text(
            "SEM_TRADING_SYMBOL,SEM_SMST_SECURITY_ID,SEM_EXM_EXCH_ID,SEM_INSTRUMENT_NAME,SEM_LOT_UNITS\n"
            "RELIANCE,2885,NSE,EQUITY,1.0\n"
        )
        ref = resolver.resolve("NIFTY", "INDEX")
        assert ref.security_id == "13"
        assert ref.exchange_segment == "IDX_I"
