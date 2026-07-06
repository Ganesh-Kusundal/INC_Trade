"""Unit tests for Dhan instrument identity — DhanInstrumentRef, resolver, invariants."""

from __future__ import annotations

import threading

import pytest
from inc_trade.domain.exceptions import InstrumentNotFoundError

from brokers.adapters.dhan.config import DHAN_SEGMENTS
from brokers.adapters.dhan.identity import DhanInstrumentRef, DhanInstrumentResolver
from brokers.adapters.dhan.invariants import assert_valid_dhan_payload

SAMPLE_CSV = (
    "SEM_TRADING_SYMBOL,SEM_SMST_SECURITY_ID,SEM_EXM_EXCH_ID,SEM_INSTRUMENT_NAME,"
    "SEM_LOT_UNITS,SEM_OPTION_TYPE,SEM_STRIKE_PRICE,SEM_EXPIRY_DATE,SM_SYMBOL_NAME\n"
    "RELIANCE,2885,NSE,EQUITY,1,,,,RELIANCE\n"
    "TCS,532,BSE,EQUITY,1,,,,TCS\n"
    "NIFTY,13,NSE,INDEX,1,,,,NIFTY\n"
    "BANKNIFTY,25,NSE,INDEX,1,,,,BANKNIFTY\n"
    "NIFTY 26 JUN 25000 CE,55000,NSE,OPTIDX,25,CE,25000,2025-06-26,NIFTY\n"
    "NIFTY 26 JUN 25000 PE,55001,NSE,OPTIDX,25,PE,25000,2025-06-26,NIFTY\n"
    "RELIANCE 2800 PE,55002,NSE,OPTSTK,1,PE,2800,2025-06-26,RELIANCE\n"
    "NIFTY 26 JUN FUT,51976,NSE,FUTIDX,25,,,2025-06-26,NIFTY\n"
    "RELIANCE 26 JUN FUT,55003,NSE,FUTSTK,1,,,2025-06-26,RELIANCE\n"
    "CRUDEOIL 26 JUN FUT,44772,MCX,FUTCOM,100,,,2025-06-26,CRUDEOIL\n"
    "GOLD 60000 CE,44800,MCX,OPTCOM,1,CE,60000,2025-06-26,GOLD\n"
)


class TestDhanInstrumentRef:
    def test_equity_ref_creation(self):
        ref = DhanInstrumentRef(
            symbol="RELIANCE",
            security_id="2885",
            exchange_segment="NSE_EQ",
        )
        assert ref.symbol == "RELIANCE"
        assert ref.security_id == "2885"
        assert ref.exchange_segment == "NSE_EQ"
        assert ref.instrument_type == "EQUITY"
        assert ref.lot_size == 1

    def test_futures_ref_creation(self):
        ref = DhanInstrumentRef(
            symbol="NIFTY 26 JUN FUT",
            security_id="51976",
            exchange_segment="NSE_FNO",
            instrument_type="FUTIDX",
            lot_size=25,
        )
        assert ref.exchange_segment == "NSE_FNO"
        assert ref.instrument_type == "FUTIDX"
        assert ref.lot_size == 25

    def test_option_ref_creation(self):
        ref = DhanInstrumentRef(
            symbol="NIFTY 26 JUN 25000 CE",
            security_id="55000",
            exchange_segment="NSE_FNO",
            instrument_type="OPTIDX",
            lot_size=25,
        )
        assert ref.exchange_segment == "NSE_FNO"
        assert ref.instrument_type == "OPTIDX"

    def test_mcx_futures_ref(self):
        ref = DhanInstrumentRef(
            symbol="CRUDEOIL 26 JUN FUT",
            security_id="44772",
            exchange_segment="MCX_COMM",
            instrument_type="FUTCOM",
            lot_size=100,
        )
        assert ref.exchange_segment == "MCX_COMM"
        assert ref.instrument_type == "FUTCOM"

    def test_mcx_option_ref(self):
        ref = DhanInstrumentRef(
            symbol="GOLD 60000 CE",
            security_id="44800",
            exchange_segment="MCX_COMM",
            instrument_type="OPTCOM",
        )
        assert ref.exchange_segment == "MCX_COMM"
        assert ref.instrument_type == "OPTCOM"

    def test_index_ref(self):
        ref = DhanInstrumentRef(
            symbol="NIFTY",
            security_id="13",
            exchange_segment="IDX_I",
        )
        assert ref.security_id == "13"
        assert ref.exchange_segment == "IDX_I"

    def test_invalid_security_id_non_digit(self):
        with pytest.raises(ValueError, match="security_id"):
            DhanInstrumentRef(
                symbol="BAD", security_id="abc", exchange_segment="NSE_EQ"
            )

    def test_empty_security_id(self):
        with pytest.raises(ValueError, match="security_id"):
            DhanInstrumentRef(symbol="BAD", security_id="", exchange_segment="NSE_EQ")

    def test_zero_security_id(self):
        with pytest.raises(ValueError, match="security_id"):
            DhanInstrumentRef(symbol="BAD", security_id="0", exchange_segment="NSE_EQ")

    def test_invalid_segment(self):
        with pytest.raises(ValueError, match="exchange_segment"):
            DhanInstrumentRef(
                symbol="BAD", security_id="123", exchange_segment="UNKNOWN"
            )

    def test_frozen(self):
        ref = DhanInstrumentRef(
            symbol="RELIANCE", security_id="2885", exchange_segment="NSE_EQ"
        )
        with pytest.raises(AttributeError):
            ref.symbol = "TCS"

    def test_security_id_str(self):
        ref = DhanInstrumentRef(
            symbol="RELIANCE", security_id="2885", exchange_segment="NSE_EQ"
        )
        assert ref.security_id_str() == "2885"
        assert isinstance(ref.security_id_str(), str)

    def test_security_id_int(self):
        ref = DhanInstrumentRef(
            symbol="RELIANCE", security_id="2885", exchange_segment="NSE_EQ"
        )
        assert ref.security_id_int() == 2885
        assert isinstance(ref.security_id_int(), int)


class TestDhanInstrumentResolver:
    def _make_resolver(self) -> DhanInstrumentResolver:
        resolver = DhanInstrumentResolver()
        resolver.load_from_csv_text(SAMPLE_CSV)
        return resolver

    def test_load_csv(self):
        resolver = self._make_resolver()
        assert resolver._loaded
        assert len(resolver._by_security_id) > 0

    def test_resolve_equity(self):
        resolver = self._make_resolver()
        ref = resolver.resolve("RELIANCE", "NSE")
        assert ref.security_id == "2885"
        assert ref.exchange_segment == "NSE_EQ"
        assert ref.instrument_type == "EQUITY"

    def test_resolve_bse_equity(self):
        resolver = self._make_resolver()
        ref = resolver.resolve("TCS", "BSE")
        assert ref.security_id == "532"
        assert ref.exchange_segment == "BSE_EQ"

    def test_resolve_futures(self):
        resolver = self._make_resolver()
        ref = resolver.resolve("NIFTY 26 JUN FUT", "NFO")
        assert ref.security_id == "51976"
        assert ref.exchange_segment == "NSE_FNO"
        assert ref.instrument_type == "FUTIDX"

    def test_resolve_option(self):
        resolver = self._make_resolver()
        ref = resolver.resolve("NIFTY 26 JUN 25000 CE", "NFO")
        assert ref.security_id == "55000"
        assert ref.exchange_segment == "NSE_FNO"
        assert ref.instrument_type == "OPTIDX"

    def test_resolve_mcx_future(self):
        resolver = self._make_resolver()
        ref = resolver.resolve("CRUDEOIL 26 JUN FUT", "MCX")
        assert ref.security_id == "44772"
        assert ref.exchange_segment == "MCX_COMM"
        assert ref.instrument_type == "FUTCOM"

    def test_resolve_mcx_option(self):
        resolver = self._make_resolver()
        ref = resolver.resolve("GOLD 60000 CE", "MCX")
        assert ref.security_id == "44800"
        assert ref.exchange_segment == "MCX_COMM"
        assert ref.instrument_type == "OPTCOM"

    def test_resolve_index(self):
        resolver = self._make_resolver()
        ref = resolver.resolve("NIFTY", "INDEX")
        assert ref.security_id == "13"
        assert ref.exchange_segment == "IDX_I"

    def test_resolve_not_found(self):
        resolver = self._make_resolver()
        with pytest.raises(InstrumentNotFoundError):
            resolver.resolve("NONEXISTENT", "NSE")

    def test_get_by_security_id(self):
        resolver = self._make_resolver()
        ref = resolver.get_by_security_id("2885")
        assert ref is not None
        assert ref.symbol == "RELIANCE"

    def test_get_by_security_id_not_found(self):
        resolver = self._make_resolver()
        ref = resolver.get_by_security_id("999999")
        assert ref is None

    def test_search(self):
        resolver = self._make_resolver()
        results = resolver.search("NIFTY", limit=10)
        assert len(results) >= 1
        symbols = {r.symbol for r in results}
        assert "NIFTY" in symbols

    def test_search_limit(self):
        resolver = self._make_resolver()
        results = resolver.search("NIFTY", limit=2)
        assert len(results) <= 2

    def test_thread_safety(self):
        resolver = self._make_resolver()
        errors = []

        def resolve_loop():
            try:
                for _ in range(50):
                    resolver.resolve("RELIANCE", "NSE")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=resolve_loop) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors

    def test_csv_columns_parsed(self):
        resolver = self._make_resolver()
        ref = resolver.resolve("NIFTY 26 JUN 25000 CE", "NFO")
        assert ref.lot_size == 25
        assert ref.instrument_type == "OPTIDX"


class TestDhanPayloadAssertion:
    def test_valid_payload_passes(self):
        payload = {"securityId": "2885", "exchangeSegment": "NSE_EQ"}
        assert_valid_dhan_payload(payload, context="test")

    def test_invalid_security_id(self):
        payload = {"securityId": "abc"}
        with pytest.raises(ValueError, match="securityId"):
            assert_valid_dhan_payload(payload, context="test")

    def test_zero_security_id(self):
        payload = {"securityId": "0"}
        with pytest.raises(ValueError, match="securityId"):
            assert_valid_dhan_payload(payload, context="test")

    def test_invalid_segment(self):
        payload = {"exchangeSegment": "UNKNOWN"}
        with pytest.raises(ValueError, match="exchangeSegment"):
            assert_valid_dhan_payload(payload, context="test")

    def test_missing_keys_no_error(self):
        payload = {"quantity": 10}
        assert_valid_dhan_payload(payload, context="test")

    def test_context_in_error_message(self):
        payload = {"securityId": "abc"}
        with pytest.raises(ValueError, match="orders.place_order"):
            assert_valid_dhan_payload(payload, context="orders.place_order")

    def test_valid_market_data_payload(self):
        payload = {"NSE_EQ": [2885]}
        assert_valid_dhan_payload(payload, context="market_data")

    def test_invalid_market_data_payload(self):
        payload = {"NSE_EQ": ["RELIANCE"]}
        with pytest.raises(ValueError, match="security_id"):
            assert_valid_dhan_payload(payload, context="market_data")

    def test_all_dhan_segments_accepted(self):
        for seg in sorted(DHAN_SEGMENTS):
            payload = {"exchangeSegment": seg}
            assert_valid_dhan_payload(payload, context=f"seg={seg}")
