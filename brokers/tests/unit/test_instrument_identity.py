"""Tests for Instrument identity (__eq__/__hash__) and InstrumentRegistry copy-on-write."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from decimal import Decimal

import pytest
from inc_trade.market.instrument import Instrument
from inc_trade.market.instrument_registry import InstrumentRegistry

# ── Instrument Identity Tests ────────────────────────────────────────────


class TestInstrumentIdentity:
    """Tests for Instrument.__eq__ and __hash__ (identity-based)."""

    def test_equality_based_on_symbol_and_exchange(self) -> None:
        inst1 = Instrument(symbol="RELIANCE", exchange="NSE")
        inst2 = Instrument(symbol="RELIANCE", exchange="NSE")
        assert inst1 == inst2

    def test_inequality_different_symbol(self) -> None:
        inst1 = Instrument(symbol="RELIANCE", exchange="NSE")
        inst2 = Instrument(symbol="NIFTY", exchange="NSE")
        assert inst1 != inst2

    def test_inequality_different_exchange(self) -> None:
        inst1 = Instrument(symbol="RELIANCE", exchange="NSE")
        inst2 = Instrument(symbol="RELIANCE", exchange="BSE")
        assert inst1 != inst2

    def test_hash_same_for_same_identity(self) -> None:
        inst1 = Instrument(symbol="RELIANCE", exchange="NSE")
        inst2 = Instrument(symbol="RELIANCE", exchange="NSE")
        assert hash(inst1) == hash(inst2)

    def test_hash_different_for_different_identity(self) -> None:
        inst1 = Instrument(symbol="RELIANCE", exchange="NSE")
        inst2 = Instrument(symbol="NIFTY", exchange="NSE")
        assert hash(inst1) != hash(inst2)

    def test_dict_key_behavior(self) -> None:
        """Same identity → same dict key."""
        inst1 = Instrument(symbol="RELIANCE", exchange="NSE")
        inst2 = Instrument(symbol="RELIANCE", exchange="NSE")
        d = {inst1: "value"}
        assert d[inst2] == "value"  # Same key

    def test_set_behavior(self) -> None:
        """Same identity → deduplicated in set."""
        inst1 = Instrument(symbol="RELIANCE", exchange="NSE")
        inst2 = Instrument(symbol="RELIANCE", exchange="NSE")
        s = {inst1, inst2}
        assert len(s) == 1

    def test_equal_different_fields(self) -> None:
        """Same identity, different other fields → still equal."""
        inst1 = Instrument(
            symbol="RELIANCE", exchange="NSE", name="Reliance Industries", lot_size=1
        )
        inst2 = Instrument(symbol="RELIANCE", exchange="NSE", name="RIL", lot_size=10)
        assert inst1 == inst2  # Identity equality, not field equality
        assert hash(inst1) == hash(inst2)

    def test_not_equal_to_non_instrument(self) -> None:
        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        assert inst != "RELIANCE"
        assert inst != None  # noqa: E711
        assert inst != 123

    def test_equality_options_use_same_identity(self) -> None:
        """Options with same symbol+exchange but different strikes are different."""
        from datetime import datetime

        opt1 = Instrument(
            symbol="NIFTY",
            exchange="NFO",
            strike=Decimal("25000"),
            option_type="CE",
            expiry=datetime(2025, 1, 30),
        )
        opt2 = Instrument(
            symbol="NIFTY",
            exchange="NFO",
            strike=Decimal("25100"),
            option_type="CE",
            expiry=datetime(2025, 1, 30),
        )
        assert opt1 != opt2  # Different composite key (strike differs)

    def test_option_vs_equity_same_symbol(self) -> None:
        """Equity 'NIFTY' on NSE vs option 'NIFTY' on NFO are different identities."""
        equity = Instrument(symbol="NIFTY", exchange="NSE")
        option = Instrument(
            symbol="NIFTY",
            exchange="NFO",
            strike=Decimal("25000"),
            option_type="CE",
            expiry=datetime(2025, 1, 30),
        )
        assert equity != option  # Different exchanges


# ── InstrumentRegistry Copy-on-Write Tests ───────────────────────────────


class TestInstrumentRegistryCopyOnWrite:
    """Tests for InstrumentRegistry with copy-on-write semantics."""

    def test_get_returns_none_for_missing(self) -> None:
        registry = InstrumentRegistry()
        assert registry.get("NSE:MISSING") is None

    def test_get_or_create_creates_and_caches(self) -> None:
        registry = InstrumentRegistry()
        inst = registry.get_or_create(
            "NSE:RELIANCE", lambda: Instrument(symbol="RELIANCE", exchange="NSE")
        )
        assert inst.symbol == "RELIANCE"
        assert registry.get("NSE:RELIANCE") is inst  # Same object

    def test_get_or_create_returns_same_object(self) -> None:
        registry = InstrumentRegistry()
        inst1 = registry.get_or_create(
            "NSE:RELIANCE", lambda: Instrument(symbol="RELIANCE", exchange="NSE")
        )
        inst2 = registry.get_or_create(
            "NSE:RELIANCE", lambda: Instrument(symbol="RELIANCE", exchange="NSE")
        )
        assert inst1 is inst2  # Identity guarantee

    def test_factory_called_only_once(self) -> None:
        registry = InstrumentRegistry()
        call_count = 0

        def factory() -> Instrument:
            nonlocal call_count
            call_count += 1
            return Instrument(symbol="RELIANCE", exchange="NSE")

        registry.get_or_create("NSE:RELIANCE", factory)
        registry.get_or_create("NSE:RELIANCE", factory)
        assert call_count == 1  # Factory called only once

    def test_get_all_returns_snapshot(self) -> None:
        registry = InstrumentRegistry()
        registry.get_or_create("NSE:A", lambda: Instrument(symbol="A", exchange="NSE"))
        registry.get_or_create("NSE:B", lambda: Instrument(symbol="B", exchange="NSE"))
        snapshot = registry.get_all()
        assert len(snapshot) == 2
        assert "NSE:A" in snapshot
        assert "NSE:B" in snapshot

    def test_clear_empties_registry(self) -> None:
        registry = InstrumentRegistry()
        registry.get_or_create(
            "NSE:RELIANCE", lambda: Instrument(symbol="RELIANCE", exchange="NSE")
        )
        assert len(registry) == 1
        registry.clear()
        assert len(registry) == 0

    def test_contains(self) -> None:
        registry = InstrumentRegistry()
        registry.get_or_create(
            "NSE:RELIANCE", lambda: Instrument(symbol="RELIANCE", exchange="NSE")
        )
        assert "NSE:RELIANCE" in registry
        assert "NSE:MISSING" not in registry

    def test_search_by_symbol(self) -> None:
        registry = InstrumentRegistry()
        rel = Instrument(symbol="RELIANCE", exchange="NSE")
        nif = Instrument(symbol="NIFTY", exchange="NSE")
        registry.register("NSE:RELIANCE", rel)
        registry.register("NSE:NIFTY", nif)
        results = registry.search("REL")
        assert rel in results
        assert nif not in results

    def test_search_by_name(self) -> None:
        registry = InstrumentRegistry()
        rel = Instrument(symbol="RELIANCE", exchange="NSE", name="Reliance Industries Ltd")
        registry.register("NSE:RELIANCE", rel)
        results = registry.search("Industries")
        assert rel in results

    def test_concurrent_reads_during_write(self) -> None:
        """Readers never see a partially-modified dict (copy-on-write guarantee)."""
        registry = InstrumentRegistry()
        registry.get_or_create("NSE:A", lambda: Instrument(symbol="A", exchange="NSE"))

        errors = []

        def writer() -> None:
            for i in range(100):
                registry.get_or_create(
                    f"NSE:W{i}",
                    lambda i=i: Instrument(symbol=f"W{i}", exchange="NSE"),
                )

        def reader() -> None:
            for _ in range(100):
                try:
                    _ = registry.get("NSE:A")
                except Exception as e:
                    errors.append(e)

        with ThreadPoolExecutor(max_workers=4) as pool:
            pool.submit(writer)
            pool.submit(writer)
            pool.submit(reader)
            pool.submit(reader)

        assert len(errors) == 0, f"Reader saw inconsistent state: {errors}"

    def test_register_existing_raises(self) -> None:
        registry = InstrumentRegistry()
        registry.register("NSE:RELIANCE", Instrument(symbol="RELIANCE", exchange="NSE"))
        with pytest.raises(ValueError, match="already registered"):
            registry.register("NSE:RELIANCE", Instrument(symbol="RELIANCE", exchange="NSE"))

    def test_repr(self) -> None:
        registry = InstrumentRegistry()
        registry.get_or_create("NSE:A", lambda: Instrument(symbol="A", exchange="NSE"))
        assert "count=1" in repr(registry)
