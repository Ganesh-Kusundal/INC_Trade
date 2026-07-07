"""Tests for Instrument with_providers() and _delegate_context removal.

Covers:
- ``with_providers()`` method on Instrument
- ``_delegate_context`` removal (only ``_context`` remains)
- Factory still works after refactor
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from brokers.market.factory import InstrumentFactory
from brokers.market.instrument import Instrument

# ── with_providers() Tests ────────────────────────────────────────────────


class TestWithProviders:
    """Instrument.with_providers() should set providers cleanly."""

    def test_sets_provider(self) -> None:
        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        provider = MagicMock()
        provider.quote.return_value = {"ltp": Decimal("2500")}

        result = inst.with_providers(provider=provider)

        assert result is inst  # returns self for chaining
        assert inst._provider is provider
        assert inst.quote() == {"ltp": Decimal("2500")}

    def test_sets_depth_provider(self) -> None:
        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        dp = MagicMock()
        dp.depth.return_value = {"bids": [], "asks": []}

        inst.with_providers(depth_provider=dp)

        assert inst._depth_provider is dp
        assert inst.depth(20) == {"bids": [], "asks": []}

    def test_sets_order_provider(self) -> None:
        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        op = MagicMock()
        op.place_order.return_value = {"order_id": "ORD001"}

        inst.with_providers(order_provider=op)

        assert inst._order_provider is op
        assert inst.buy(quantity=10) == {"order_id": "ORD001"}

    def test_sets_historical_provider(self) -> None:
        from datetime import datetime

        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        hp = MagicMock()
        hp.get_candles.return_value = []

        inst.with_providers(historical_provider=hp)

        assert inst._historical_provider is hp
        result = inst.ohlcv(datetime(2024, 1, 1), datetime(2024, 1, 2), "1D")
        assert result == []

    def test_sets_streaming_provider(self) -> None:
        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        sp = MagicMock()

        inst.with_providers(streaming_provider=sp)

        assert inst._streaming_provider is sp

    def test_sets_context(self) -> None:
        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        ctx = MagicMock()

        inst.with_providers(context=ctx)

        assert inst._context is ctx

    def test_none_is_noop(self) -> None:
        """Passing None for all providers should not change anything."""
        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        original_id = id(inst)

        inst.with_providers()

        assert id(inst) == original_id
        assert inst._provider is None
        assert inst._depth_provider is None
        assert inst._order_provider is None

    def test_partial_update_keeps_existing(self) -> None:
        """Setting only one provider should not clear others."""
        provider = MagicMock()
        dp = MagicMock()

        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        inst.with_providers(provider=provider)
        inst.with_providers(depth_provider=dp)

        assert inst._provider is provider  # unchanged
        assert inst._depth_provider is dp  # newly set

    def test_chaining_quote(self) -> None:
        """with_providers() should return self for chaining."""
        provider = MagicMock()
        provider.quote.return_value = {"ltp": Decimal("100")}

        result = (
            Instrument(symbol="RELIANCE", exchange="NSE").with_providers(provider=provider).quote()
        )

        assert result == {"ltp": Decimal("100")}

    def test_clearing_provider(self) -> None:
        """Setting a provider to a sentinel object clears it."""
        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        provider = MagicMock()
        inst.with_providers(provider=provider)
        assert inst._provider is provider

        sentinel = object()
        inst.with_providers(provider=sentinel)
        assert inst._provider is sentinel


# ── _delegate_context Removal Tests ───────────────────────────────────────


class TestNoDelegateContext:
    """_delegate_context should no longer exist on Instrument."""

    def test_no_delegate_context_attribute(self) -> None:
        """Instrument should not have _delegate_context."""
        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        assert not hasattr(inst, "_delegate_context")

    def test_context_is_set_not_delegate(self) -> None:
        """_context should be set, not _delegate_context."""
        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        ctx = MagicMock()
        object.__setattr__(inst, "_context", ctx)
        assert inst._context is ctx

    def test_factory_sets_context_not_delegate(self) -> None:
        """InstrumentFactory should set _context, not _delegate_context."""
        inst = InstrumentFactory.create(
            symbol="NIFTY",
            exchange="NSE",
        )
        # _context should work (may be None since no context arg passed)
        assert hasattr(inst, "_context")
        assert not hasattr(inst, "_delegate_context")


# ── Factory Integration Tests ─────────────────────────────────────────────


class TestFactoryRefactored:
    """Factory should still work after with_providers() refactor."""

    def test_factory_creates_equity(self) -> None:
        inst = InstrumentFactory.create(
            symbol="RELIANCE",
            exchange="NSE",
        )
        assert inst.is_equity()
        assert inst.symbol == "RELIANCE"

    def test_factory_with_provider_delegates_quote(self) -> None:
        provider = MagicMock()
        provider.quote.return_value = {"ltp": Decimal("2500")}
        inst = InstrumentFactory.create(
            symbol="RELIANCE",
            exchange="NSE",
            provider=provider,
        )
        assert inst._provider is provider
        assert inst.quote() == {"ltp": Decimal("2500")}

    def test_factory_with_depth_provider(self) -> None:
        dp = MagicMock()
        inst = InstrumentFactory.create(
            symbol="RELIANCE",
            exchange="NSE",
            depth_provider=dp,
        )
        assert inst._depth_provider is dp

    def test_factory_with_order_provider(self) -> None:
        op = MagicMock()
        op.place_order.return_value = {"order_id": "ORD001"}
        inst = InstrumentFactory.create(
            symbol="RELIANCE",
            exchange="NSE",
            order_provider=op,
        )
        assert inst._order_provider is op
        assert inst.buy(quantity=10) == {"order_id": "ORD001"}


# ── Instrument Identity Tests ─────────────────────────────────────────────


class TestInstrumentIdentity:
    """Instrument identity should be preserved after with_providers()."""

    def test_hash_unchanged(self) -> None:
        """Adding providers should not change hash."""
        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        h1 = hash(inst)
        inst.with_providers(provider=MagicMock())
        h2 = hash(inst)
        assert h1 == h2

    def test_eq_unchanged(self) -> None:
        """Adding providers should not affect equality."""
        inst1 = Instrument(symbol="RELIANCE", exchange="NSE")
        inst2 = Instrument(symbol="RELIANCE", exchange="NSE")
        inst1.with_providers(provider=MagicMock())
        assert inst1 == inst2

    def test_composite_key_unchanged(self) -> None:
        """Composite key should remain the same."""
        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        assert inst.composite_key == "NSE:RELIANCE"
        inst.with_providers(provider=MagicMock())
        assert inst.composite_key == "NSE:RELIANCE"
