"""Comprehensive bidirectional symbol mapping tests.

Tests security_id → canonical_symbol and canonical_symbol → security_id
for ALL instrument segments: Equity, Index, F&O Options, F&O Futures,
MCX Commodity, BSE F&O, Currency.
"""

from __future__ import annotations

import pytest

from brokers.dhan.domain import Exchange, InstrumentType, OptionType
from brokers.dhan.exceptions import InstrumentNotFoundError
from brokers.dhan.resolver import SymbolResolver

# ---------------------------------------------------------------------------
# Helper: load resolver from SAMPLE_ROWS via conftest
# ---------------------------------------------------------------------------


class TestForwardMapping:
    """symbol → security_id (forward lookup)."""

    # ── Equity ──

    def test_equity_nse_by_trading_symbol(self, resolver):
        inst = resolver.resolve("RELIANCE", "NSE")
        assert inst.security_id == "2885"
        assert inst.exchange == Exchange.NSE
        assert inst.instrument_type == InstrumentType.EQUITY

    def test_equity_bse_by_trading_symbol(self, resolver):
        inst = resolver.resolve("RELIANCE", "BSE")
        assert inst.security_id == "532"
        assert inst.exchange == Exchange.BSE

    def test_equity_by_custom_symbol(self, resolver):
        """SEM_CUSTOM_SYMBOL ('Reliance Industries') should also resolve."""
        inst = resolver.get_by_symbol("RELIANCE INDUSTRIES", "NSE")
        assert inst is not None
        assert inst.security_id == "2885"

    # ── Index ──

    def test_index_by_trading_symbol(self, resolver):
        inst = resolver.resolve("NIFTY", "INDEX")
        assert inst.security_id == "13"
        assert inst.exchange == Exchange.INDEX
        assert inst.instrument_type == InstrumentType.EQUITY

    def test_index_by_custom_symbol(self, resolver):
        inst = resolver.get_by_symbol("NIFTY 50", "INDEX")
        assert inst is not None
        assert inst.security_id == "13"

    # ── NSE F&O Options ──

    def test_option_ce_by_trading_symbol(self, resolver):
        inst = resolver.resolve("NIFTY-26Jun2026-25000-CE", "NFO")
        assert inst.security_id == "55000"
        assert inst.instrument_type == InstrumentType.OPTION
        assert inst.option_type == OptionType.CALL
        assert float(inst.strike_price) == 25000.0
        assert inst.underlying == "NIFTY"

    def test_option_pe_by_trading_symbol(self, resolver):
        inst = resolver.resolve("NIFTY-26Jun2026-25000-PE", "NFO")
        assert inst.security_id == "55001"
        assert inst.option_type == OptionType.PUT

    def test_option_by_custom_symbol_call(self, resolver):
        """SEM_CUSTOM_SYMBOL format: 'NIFTY 26 JUN 25000 CALL'."""
        inst = resolver.get_by_symbol("NIFTY 26 JUN 25000 CALL", "NFO")
        assert inst is not None
        assert inst.security_id == "55000"

    def test_option_by_custom_symbol_ce_variant(self, resolver):
        """User types 'NIFTY 26 JUN 25000 CE' — should map to CALL contract."""
        inst = resolver.get_by_symbol("NIFTY 26 JUN 25000 CE", "NFO")
        assert inst is not None
        assert inst.security_id == "55000"

    def test_option_by_custom_symbol_put(self, resolver):
        inst = resolver.get_by_symbol("NIFTY 26 JUN 25000 PUT", "NFO")
        assert inst is not None
        assert inst.security_id == "55001"

    def test_option_by_custom_symbol_pe_variant(self, resolver):
        inst = resolver.get_by_symbol("NIFTY 26 JUN 25000 PE", "NFO")
        assert inst is not None
        assert inst.security_id == "55001"

    def test_option_by_compact_format(self, resolver):
        """Compact form: NIFTY26JUN202625000CE."""
        inst = resolver.get_by_symbol("NIFTY26JUN202625000CE", "NFO")
        assert inst is not None
        assert inst.security_id == "55000"

    def test_option_by_weekly_format(self, resolver):
        """Weekly form: NIFTY2662625000CE (yy+month_char+dd)."""
        inst = resolver.get_by_symbol("NIFTY2662625000CE", "NFO")
        assert inst is not None
        assert inst.security_id == "55000"

    # ── Stock F&O ──

    def test_stock_option_by_trading_symbol(self, resolver):
        inst = resolver.resolve("RELIANCE-26Jun2026-3000-CE", "NFO")
        assert inst.security_id == "60000"
        assert inst.instrument_type == InstrumentType.OPTION
        assert inst.underlying == "RELIANCE"

    def test_stock_option_by_custom_symbol(self, resolver):
        inst = resolver.get_by_symbol("RELIANCE 26 JUN 3000 CALL", "NFO")
        assert inst is not None
        assert inst.security_id == "60000"

    def test_stock_option_ce_variant(self, resolver):
        inst = resolver.get_by_symbol("RELIANCE 26 JUN 3000 CE", "NFO")
        assert inst is not None
        assert inst.security_id == "60000"

    def test_stock_future_by_trading_symbol(self, resolver):
        inst = resolver.resolve("RELIANCE-26Jun2026-FUT", "NFO")
        assert inst.security_id == "60100"
        assert inst.instrument_type == InstrumentType.FUTURE
        assert inst.underlying == "RELIANCE"

    def test_stock_future_by_custom_symbol(self, resolver):
        inst = resolver.get_by_symbol("RELIANCE JUN FUT", "NFO")
        assert inst is not None
        assert inst.security_id == "60100"

    # ── NSE F&O Futures ──

    def test_index_future_by_trading_symbol(self, resolver):
        inst = resolver.resolve("NIFTY-26Jun2026-FUT", "NFO")
        assert inst.security_id == "55100"
        assert inst.instrument_type == InstrumentType.FUTURE

    def test_index_future_by_custom_symbol(self, resolver):
        inst = resolver.get_by_symbol("NIFTY JUN FUT", "NFO")
        assert inst is not None
        assert inst.security_id == "55100"

    # ── MCX Commodity Futures ──

    def test_mcx_future_by_trading_symbol(self, resolver):
        inst = resolver.resolve("CRUDEOIL-18Jun2026-FUT", "MCX")
        assert inst.security_id == "466500"
        assert inst.instrument_type == InstrumentType.FUTURE

    def test_mcx_future_by_custom_symbol(self, resolver):
        inst = resolver.get_by_symbol("CRUDEOIL JUN FUT", "MCX")
        assert inst is not None
        assert inst.security_id == "466500"

    def test_mcx_future_by_sm_symbol_name(self, resolver):
        """SM_SYMBOL_NAME='CRUDEOIL' should resolve to a CRUDEOIL instrument."""
        inst = resolver.get_by_symbol("CRUDEOIL", "MCX")
        assert inst is not None
        assert inst.sm_symbol_name == "CRUDEOIL"

    def test_goldm_by_sm_symbol_name(self, resolver):
        """SM_SYMBOL_NAME='GOLDM' should resolve to the GOLDM future."""
        inst = resolver.get_by_symbol("GOLDM", "MCX")
        assert inst is not None
        assert inst.security_id == "466584"
        assert inst.sm_symbol_name == "GOLDM"

    # ── MCX Commodity Options ──

    def test_mcx_option_by_trading_symbol(self, resolver):
        inst = resolver.resolve("CRUDEOIL-18Jun2026-5000-CE", "MCX")
        assert inst.security_id == "466600"
        assert inst.instrument_type == InstrumentType.OPTION
        assert inst.option_type == OptionType.CALL

    def test_mcx_option_by_custom_symbol(self, resolver):
        inst = resolver.get_by_symbol("CRUDEOIL 18 JUN 5000 CALL", "MCX")
        assert inst is not None
        assert inst.security_id == "466600"

    def test_mcx_option_ce_variant(self, resolver):
        inst = resolver.get_by_symbol("CRUDEOIL 18 JUN 5000 CE", "MCX")
        assert inst is not None
        assert inst.security_id == "466600"

    # ── BSE F&O ──

    def test_bse_option_by_trading_symbol(self, resolver):
        inst = resolver.resolve("SENSEX-26Jun2026-80000-CE", "BFO")
        assert inst.security_id == "70000"
        assert inst.instrument_type == InstrumentType.OPTION
        assert inst.underlying == "SENSEX"

    def test_bse_option_by_custom_symbol(self, resolver):
        inst = resolver.get_by_symbol("SENSEX 26 JUN 80000 CALL", "BFO")
        assert inst is not None
        assert inst.security_id == "70000"

    def test_bse_option_ce_variant(self, resolver):
        inst = resolver.get_by_symbol("SENSEX 26 JUN 80000 CE", "BFO")
        assert inst is not None
        assert inst.security_id == "70000"

    # ── Currency ──

    def test_currency_future_by_trading_symbol(self, resolver):
        inst = resolver.resolve("USDINR-26Jun2026-FUT", "CDS")
        assert inst.security_id == "80000"
        assert inst.instrument_type == InstrumentType.FUTURE

    def test_currency_future_by_custom_symbol(self, resolver):
        inst = resolver.get_by_symbol("USDINR JUN FUT", "CDS")
        assert inst is not None
        assert inst.security_id == "80000"

    def test_currency_future_by_sm_symbol_name(self, resolver):
        """SM_SYMBOL_NAME='USDINR' should resolve to a USDINR instrument."""
        inst = resolver.get_by_symbol("USDINR", "CDS")
        assert inst is not None
        assert inst.sm_symbol_name == "USDINR"

    def test_currency_option_by_trading_symbol(self, resolver):
        inst = resolver.resolve("USDINR-26Jun2026-85-CE", "CDS")
        assert inst.security_id == "80100"
        assert inst.instrument_type == InstrumentType.OPTION

    def test_currency_option_by_custom_symbol(self, resolver):
        inst = resolver.get_by_symbol("USDINR 26 JUN 85 CALL", "CDS")
        assert inst is not None
        assert inst.security_id == "80100"


class TestReverseMapping:
    """security_id → Instrument (reverse lookup)."""

    @pytest.mark.parametrize(
        "sec_id,expected_symbol,expected_exchange",
        [
            ("13", "NIFTY", Exchange.INDEX),
            ("2885", "RELIANCE", Exchange.NSE),
            ("532", "RELIANCE", Exchange.BSE),
            ("55000", "NIFTY-26Jun2026-25000-CE", Exchange.NFO),
            ("55001", "NIFTY-26Jun2026-25000-PE", Exchange.NFO),
            ("55100", "NIFTY-26Jun2026-FUT", Exchange.NFO),
            ("466500", "CRUDEOIL-18Jun2026-FUT", Exchange.MCX),
            ("466501", "CRUDEOIL-20Jul2026-FUT", Exchange.MCX),
            ("466600", "CRUDEOIL-18Jun2026-5000-CE", Exchange.MCX),
            ("466583", "GOLD AUG FUT", Exchange.MCX),
            ("466584", "GOLDM-03Jul2026-FUT", Exchange.MCX),
            ("70000", "SENSEX-26Jun2026-80000-CE", Exchange.BFO),
            ("80000", "USDINR-26Jun2026-FUT", Exchange.CDS),
            ("80100", "USDINR-26Jun2026-85-CE", Exchange.CDS),
            ("60000", "RELIANCE-26Jun2026-3000-CE", Exchange.NFO),
            ("60100", "RELIANCE-26Jun2026-FUT", Exchange.NFO),
        ],
    )
    def test_reverse_by_security_id(self, resolver, sec_id, expected_symbol, expected_exchange):
        inst = resolver.get_by_security_id(sec_id)
        assert inst is not None, f"security_id={sec_id} not found"
        assert inst.symbol == expected_symbol
        assert inst.exchange == expected_exchange


class TestBidirectionalRoundTrip:
    """Verify symbol→sid→symbol round-trip for every fixture row."""

    @pytest.mark.parametrize(
        "sec_id",
        [
            "13",
            "2885",
            "532",
            "55000",
            "55001",
            "55100",
            "466500",
            "466501",
            "466600",
            "466583",
            "466584",
            "70000",
            "80000",
            "80100",
            "60000",
            "60100",
        ],
    )
    def test_round_trip(self, resolver, sec_id):
        # Reverse: security_id → Instrument
        inst = resolver.get_by_security_id(sec_id)
        assert inst is not None, f"security_id={sec_id} not found in reverse map"

        # Forward: symbol + exchange → Instrument
        forward = resolver.get_by_symbol(inst.symbol, inst.exchange.value)
        assert forward is not None, (
            f"symbol={inst.symbol}, exchange={inst.exchange.value} not found in forward map"
        )
        assert forward.security_id == sec_id


class TestSmSymbolName:
    """Tests that SM_SYMBOL_NAME is correctly propagated and usable."""

    def test_equity_has_sm_symbol_name(self, resolver):
        inst = resolver.get_by_security_id("2885")
        assert inst is not None
        assert inst.sm_symbol_name == "RELIANCE INDUSTRIES LTD"

    def test_mcx_has_sm_symbol_name(self, resolver):
        inst = resolver.get_by_security_id("466500")
        assert inst is not None
        assert inst.sm_symbol_name == "CRUDEOIL"

    def test_currency_has_sm_symbol_name(self, resolver):
        inst = resolver.get_by_security_id("80000")
        assert inst is not None
        assert inst.sm_symbol_name == "USDINR"

    def test_option_has_sm_symbol_name(self, resolver):
        inst = resolver.get_by_security_id("55000")
        assert inst is not None
        assert inst.sm_symbol_name == "NIFTY"

    def test_underlying_derived_from_sm_symbol_name(self, resolver):
        """underlying should come from SM_SYMBOL_NAME, not SEM_CUSTOM_SYMBOL."""
        inst = resolver.get_by_security_id("466500")
        assert inst.underlying == "CRUDEOIL"  # from SM_SYMBOL_NAME, not 'CRUDEOIL' from canonical


class TestUnderlyingIndex:
    """Tests the _by_underlying index for futures and options."""

    def test_get_futures_returns_sorted(self, resolver):
        futures = resolver.get_futures("CRUDEOIL", "MCX")
        assert len(futures) == 2
        assert futures[0].expiry < futures[1].expiry

    def test_get_futures_nifty(self, resolver):
        futures = resolver.get_futures("NIFTY", "NFO")
        assert len(futures) >= 1
        assert all(f.instrument_type == InstrumentType.FUTURE for f in futures)

    def test_get_futures_reliance(self, resolver):
        futures = resolver.get_futures("RELIANCE", "NFO")
        assert len(futures) >= 1
        assert futures[0].security_id == "60100"

    def test_get_futures_usdinr(self, resolver):
        futures = resolver.get_futures("USDINR", "CDS")
        assert len(futures) >= 1
        assert futures[0].security_id == "80000"

    def test_get_futures_expiries(self, resolver):
        expiries = resolver.get_futures_expiries("CRUDEOIL", "MCX")
        assert len(expiries) == 2
        assert expiries[0] < expiries[1]


class TestExchangeNormalization:
    """Tests that various exchange format strings resolve correctly."""

    @pytest.mark.parametrize(
        "exchange_str",
        [
            "NSE",
            "NSE_EQ",
            "nse",
            "Nse",
        ],
    )
    def test_equity_exchange_variants(self, resolver, exchange_str):
        inst = resolver.get_by_symbol("RELIANCE", exchange_str)
        assert inst is not None
        assert inst.security_id == "2885"

    @pytest.mark.parametrize(
        "exchange_str",
        [
            "NFO",
            "NSE_FNO",
            "nfo",
        ],
    )
    def test_fno_exchange_variants(self, resolver, exchange_str):
        inst = resolver.get_by_symbol("NIFTY-26Jun2026-25000-CE", exchange_str)
        assert inst is not None
        assert inst.security_id == "55000"

    @pytest.mark.parametrize(
        "exchange_str",
        [
            "MCX",
            "MCX_COMM",
            "mcx",
        ],
    )
    def test_mcx_exchange_variants(self, resolver, exchange_str):
        inst = resolver.get_by_symbol("CRUDEOIL-18Jun2026-FUT", exchange_str)
        assert inst is not None
        assert inst.security_id == "466500"

    @pytest.mark.parametrize(
        "exchange_str",
        [
            "CDS",
            "NSE_CURRENCY",
            "cds",
        ],
    )
    def test_currency_exchange_variants(self, resolver, exchange_str):
        inst = resolver.get_by_symbol("USDINR-26Jun2026-FUT", exchange_str)
        assert inst is not None
        assert inst.security_id == "80000"

    @pytest.mark.parametrize(
        "exchange_str",
        [
            "BFO",
            "BSE_FNO",
            "bfo",
        ],
    )
    def test_bfo_exchange_variants(self, resolver, exchange_str):
        inst = resolver.get_by_symbol("SENSEX-26Jun2026-80000-CE", exchange_str)
        assert inst is not None
        assert inst.security_id == "70000"


class TestEdgeCases:
    """Edge cases and error handling."""

    def test_unknown_symbol_raises(self, resolver):
        with pytest.raises(InstrumentNotFoundError):
            resolver.resolve("DOESNOTEXIST", "NSE")

    def test_unknown_security_id_returns_none(self, resolver):
        assert resolver.get_by_security_id("999999999") is None

    def test_empty_symbol(self, resolver):
        assert resolver.get_by_symbol("", "NSE") is None

    def test_unknown_exchange_raises(self, resolver):
        with pytest.raises(InstrumentNotFoundError):
            resolver.resolve("RELIANCE", "UNKNOWN_EXCHANGE")

    def test_case_insensitive_symbol(self, resolver):
        inst = resolver.get_by_symbol("reliance", "NSE")
        assert inst is not None
        assert inst.security_id == "2885"

    def test_symbol_with_spaces(self, resolver):
        inst = resolver.get_by_symbol("  RELIANCE  ", "NSE")
        assert inst is not None
        assert inst.security_id == "2885"

    def test_row_without_sm_symbol_name_still_works(self):
        """Rows without SM_SYMBOL_NAME should still load (backward compatibility)."""
        r = SymbolResolver()
        r.load_from_rows(
            [
                {
                    "SEM_TRADING_SYMBOL": "TESTSTOCK",
                    "SEM_SMST_SECURITY_ID": "99999",
                    "SEM_EXM_EXCH_ID": "NSE_EQ",
                    "SEM_INSTRUMENT_NAME": "EQUITY",
                    "SEM_LOT_UNITS": 1,
                    "SEM_TICK_SIZE": 0.05,
                }
            ]
        )
        inst = r.get_by_security_id("99999")
        assert inst is not None
        assert inst.sm_symbol_name is None
        assert inst.symbol == "TESTSTOCK"
