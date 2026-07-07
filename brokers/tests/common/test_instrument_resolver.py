"""Tests for brokers.common.instrument_resolver.

Covers:
  - ResolvedInstrument dataclass
  - InMemoryInstrumentResolver: register, resolve, search, stats
  - Alternate key generation (option/future compact symbols)
  - Conflict resolution (EQUITY > OPTIONS priority)
  - InstrumentNotFoundError
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from brokers.common.instrument_resolver import (
    InstrumentNotFoundError,
    InMemoryInstrumentResolver,
    ResolvedInstrument,
)
from brokers.domain.enums import Exchange, InstrumentType


# ── Fixtures ───────────────────────────────────────────────────────────────


def _make_inst(
    symbol: str = "RELIANCE",
    exchange: Exchange = Exchange.NSE,
    broker_id: str = "3456",
    segment: str = "NSE_EQ",
    instrument_type: InstrumentType = InstrumentType.EQUITY,
    trading_symbol: str = "RELIANCE",
    **kwargs,
) -> ResolvedInstrument:
    return ResolvedInstrument(
        symbol=symbol,
        exchange=exchange,
        broker_id=broker_id,
        segment=segment,
        instrument_type=instrument_type,
        trading_symbol=trading_symbol,
        **kwargs,
    )


@pytest.fixture
def resolver() -> InMemoryInstrumentResolver:
    return InMemoryInstrumentResolver(broker_name="test")


@pytest.fixture
def loaded_resolver() -> InMemoryInstrumentResolver:
    r = InMemoryInstrumentResolver(broker_name="test")
    r.register_many([
        _make_inst("RELIANCE", Exchange.NSE, "3456", "NSE_EQ"),
        _make_inst("TCS", Exchange.NSE, "1001", "NSE_EQ"),
        _make_inst("INFY", Exchange.NSE, "1002", "NSE_EQ"),
        _make_inst("NIFTY", Exchange.INDEX, "13", "IDX_I", InstrumentType.INDEX),
    ])
    return r


# ── ResolvedInstrument tests ───────────────────────────────────────────────


class TestResolvedInstrument:
    def test_immutable(self):
        inst = _make_inst()
        with pytest.raises(AttributeError):
            inst.symbol = "TCS"  # type: ignore

    def test_defaults(self):
        inst = _make_inst()
        assert inst.lot_size == 1
        assert inst.tick_size == Decimal("0.05")
        assert inst.instrument_type == InstrumentType.EQUITY
        assert inst.isin == ""
        assert inst.expiry is None
        assert inst.strike is None


# ── Register & Resolve tests ───────────────────────────────────────────────


class TestRegisterAndResolve:
    def test_resolve_by_symbol(self, loaded_resolver):
        inst = loaded_resolver.resolve("RELIANCE", Exchange.NSE)
        assert inst.broker_id == "3456"
        assert inst.exchange == Exchange.NSE

    def test_resolve_strips_spaces(self, loaded_resolver):
        loaded_resolver.register_one(_make_inst("HDFC BANK", Exchange.NSE, "5001"))
        inst = loaded_resolver.resolve("HDFCBANK", Exchange.NSE)
        assert inst.broker_id == "5001"

    def test_resolve_strips_dashes(self, loaded_resolver):
        loaded_resolver.register_one(_make_inst("SBIN-EQ", Exchange.NSE, "5002"))
        inst = loaded_resolver.resolve("SBINEQ", Exchange.NSE)
        assert inst is not None

    def test_resolve_uppercase(self, loaded_resolver):
        inst = loaded_resolver.resolve("reliance", Exchange.NSE)
        assert inst.broker_id == "3456"

    def test_resolve_by_trading_symbol(self, loaded_resolver):
        loaded_resolver.register_one(
            _make_inst("CANBK", Exchange.NSE, "5003", trading_symbol="CANBK-EQ")
        )
        inst = loaded_resolver.resolve("CANBK-EQ", Exchange.NSE)
        assert inst.broker_id == "5003"

    def test_resolve_not_found_raises(self, resolver):
        with pytest.raises(InstrumentNotFoundError):
            resolver.resolve("NONEXISTENT", Exchange.NSE)

    def test_resolve_by_broker_id(self, loaded_resolver):
        inst = loaded_resolver.resolve_by_broker_id("3456")
        assert inst.symbol == "RELIANCE"

    def test_resolve_by_broker_id_not_found(self, loaded_resolver):
        with pytest.raises(InstrumentNotFoundError):
            loaded_resolver.resolve_by_broker_id("999999")

    def test_register_many_returns_count(self, resolver):
        count = resolver.register_many([
            _make_inst("A", Exchange.NSE, "1"),
            _make_inst("B", Exchange.NSE, "2"),
            _make_inst("C", Exchange.NSE, "3"),
        ])
        assert count == 3

    def test_register_skips_empty_broker_id(self, resolver):
        count = resolver.register_many([
            _make_inst("A", Exchange.NSE, "1"),
            ResolvedInstrument(
                symbol="B", exchange=Exchange.NSE, broker_id="", segment="NSE_EQ",
            ),
        ])
        assert count == 1


# ── Conflict resolution tests ──────────────────────────────────────────────


class TestConflictResolution:
    def test_equity_overrides_options(self, resolver):
        # Register option first, then equity with same symbol
        resolver.register_one(_make_inst(
            "NIFTY", Exchange.NFO, "111", "NSE_FNO",
            InstrumentType.OPTIONS, trading_symbol="NIFTY26JUNFUT",
        ))
        resolver.register_one(_make_inst(
            "NIFTY", Exchange.INDEX, "13", "IDX_I",
            InstrumentType.INDEX, trading_symbol="NIFTY",
        ))
        inst = resolver.resolve("NIFTY", Exchange.INDEX)
        # INDEX should win over OPTIONS
        assert inst.instrument_type == InstrumentType.INDEX
        assert inst.broker_id == "13"

    def test_options_does_not_override_equity(self, resolver):
        # Register equity first
        resolver.register_one(_make_inst(
            "RELIANCE", Exchange.NSE, "3456", "NSE_EQ",
            InstrumentType.EQUITY,
        ))
        # Then option with same symbol (should NOT override)
        resolver.register_one(_make_inst(
            "RELIANCE", Exchange.NFO, "999", "NSE_FNO",
            InstrumentType.OPTIONS, trading_symbol="RELIANCE26JUNFUT",
        ))
        inst = resolver.resolve("RELIANCE", Exchange.NSE)
        assert inst.broker_id == "3456"
        assert inst.instrument_type == InstrumentType.EQUITY


# ── Search tests ───────────────────────────────────────────────────────────


class TestSearch:
    def test_search_by_symbol(self, loaded_resolver):
        results = loaded_resolver.search("RELI", limit=10)
        assert len(results) >= 1
        assert any(r.symbol == "RELIANCE" for r in results)

    def test_search_limit(self, loaded_resolver):
        loaded_resolver.register_one(_make_inst("RELIANCE1", Exchange.NSE, "7001"))
        loaded_resolver.register_one(_make_inst("RELIANCE2", Exchange.NSE, "7002"))
        loaded_resolver.register_one(_make_inst("RELIANCE3", Exchange.NSE, "7003"))
        results = loaded_resolver.search("RELI", limit=2)
        assert len(results) <= 2

    def test_search_no_results(self, loaded_resolver):
        results = loaded_resolver.search("ZZZZZ")
        assert len(results) == 0

    def test_search_case_insensitive(self, loaded_resolver):
        results = loaded_resolver.search("reli")
        assert len(results) >= 1


# ── Stats tests ────────────────────────────────────────────────────────────


class TestStats:
    def test_stats_total(self, loaded_resolver):
        stats = loaded_resolver.stats()
        assert stats["total"] == 4
        assert "by_type" in stats
        assert stats["by_type"].get("EQUITY", 0) == 3
        assert stats["by_type"].get("INDEX", 0) == 1

    def test_is_loaded_false_initially(self, resolver):
        assert resolver.is_loaded is False

    def test_is_loaded_true_after_register(self, resolver):
        resolver.register_one(_make_inst("A", Exchange.NSE, "1"))
        assert resolver.is_loaded is True


# ── Alternate key generation tests ─────────────────────────────────────────


class TestAlternateKeys:
    def test_option_compact_key(self, resolver):
        inst = _make_inst(
            "NIFTY 26 JUN 15900 CE", Exchange.NFO, "12345", "NSE_FO",
            InstrumentType.OPTIONS,
            trading_symbol="NIFTY26JUN15900CE",
            expiry="2026-06-26",
            strike=Decimal("15900"),
            underlying="NIFTY",
        )
        resolver.register_one(inst)
        # Should be resolvable by compact symbol
        result = resolver.resolve("NIFTY26JUN15900CE", Exchange.NFO)
        assert result.broker_id == "12345"

    def test_future_compact_key(self, resolver):
        inst = _make_inst(
            "NIFTY FUT", Exchange.NFO, "12346", "NSE_FO",
            InstrumentType.FUTURES,
            trading_symbol="NIFTY26JUNFUT",
            expiry="2026-06-26",
            underlying="NIFTY",
        )
        resolver.register_one(inst)
        result = resolver.resolve("NIFTY26JUNFUT", Exchange.NFO)
        assert result.broker_id == "12346"

    def test_call_put_standardization(self, resolver):
        inst = _make_inst(
            "NIFTY26JUN15900CE", Exchange.NFO, "12347", "NSE_FO",
            InstrumentType.OPTIONS,
            trading_symbol="NIFTY26JUN15900CE",
            expiry="2026-06-26",
            strike=Decimal("15900"),
            underlying="NIFTY",
        )
        resolver.register_one(inst)
        # Should NOT find with CALL suffix (we register with CE)
        # But the alternate key generator should add CALL variant
        result = resolver.resolve("NIFTY26JUN15900CALL", Exchange.NFO)
        assert result.broker_id == "12347"
