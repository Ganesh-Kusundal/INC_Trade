"""Tests for the Instrument Decorator Pipeline (Phase 1).

Covers:
- ``InstrumentDecorator`` base class delegation
- ``Depth20Decorator``, ``Depth30Decorator``, ``Depth200Decorator``
- ``CachedDecorator`` with TTL
- ``LoggedDecorator``
- ``with_depth()``, ``with_cache()``, ``with_logging()`` helpers
- Decorator composition (stacking)
"""

from __future__ import annotations

import logging
import time
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from inc_trade.market.cache_decorator import CachedDecorator
from inc_trade.market.decorators import (
    InstrumentDecorator,
    with_cache,
    with_depth,
    with_logging,
)
from inc_trade.market.depth_decorators import (
    Depth20Decorator,
    Depth30Decorator,
    Depth200Decorator,
)
from inc_trade.market.instrument import Instrument
from inc_trade.market.log_decorator import LoggedDecorator

# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def mock_instrument() -> Instrument:
    """Create a minimal instrument with a mocked provider."""
    inst = Instrument(
        symbol="RELIANCE",
        exchange="NSE",
        name="Reliance Industries",
        lot_size=1,
        tick_size=Decimal("0.05"),
    )
    provider = MagicMock()
    provider.quote.return_value = {"symbol": "RELIANCE", "ltp": Decimal("2500")}
    provider.ltp.return_value = Decimal("2500")
    provider.depth.return_value = {
        "bids": [{"price": Decimal("2499"), "quantity": 100}],
        "asks": [{"price": Decimal("2501"), "quantity": 50}],
    }
    provider.place_order.return_value = {"order_id": "ORD123", "success": True}
    object.__setattr__(inst, "_provider", provider)
    object.__setattr__(inst, "_depth_provider", provider)
    object.__setattr__(inst, "_order_provider", provider)
    return inst


@pytest.fixture
def mock_depth_provider() -> MagicMock:
    """A DepthProvider that returns canned depth data."""
    provider = MagicMock()
    provider.depth.return_value = {
        "bids": [{"price": Decimal("2499"), "quantity": 100, "orders": 5}],
        "asks": [{"price": Decimal("2501"), "quantity": 50, "orders": 3}],
    }
    return provider


# ── InstrumentDecorator Base ─────────────────────────────────────────────


class TestInstrumentDecorator:
    """InstrumentDecorator should delegate all unknown attributes."""

    def test_decorator_delegates_quote(self, mock_instrument: Instrument) -> None:
        decorator = InstrumentDecorator(mock_instrument)
        result = decorator.quote()
        assert result is not None

    def test_decorator_delegates_ltp(self, mock_instrument: Instrument) -> None:
        decorator = InstrumentDecorator(mock_instrument)
        result = decorator.ltp()
        assert result == Decimal("2500")

    def test_decorator_delegates_symbol(self, mock_instrument: Instrument) -> None:
        decorator = InstrumentDecorator(mock_instrument)
        assert decorator.symbol == "RELIANCE"

    def test_decorator_delegates_composite_key(
        self,
        mock_instrument: Instrument,
    ) -> None:
        decorator = InstrumentDecorator(mock_instrument)
        assert decorator.composite_key == "NSE:RELIANCE"

    def test_decorator_repr(self, mock_instrument: Instrument) -> None:
        decorator = InstrumentDecorator(mock_instrument)
        assert "InstrumentDecorator" in repr(decorator)
        assert "NSE:RELIANCE" in repr(decorator)

    def test_decorator_wraps_correct_instrument(
        self,
        mock_instrument: Instrument,
    ) -> None:
        decorator = InstrumentDecorator(mock_instrument)
        assert decorator._wrapped is mock_instrument


# ── Depth Decorators ─────────────────────────────────────────────────────


class TestDepthDecorator:
    """DepthDecorator should add configurable depth levels."""

    def test_depth_decorator_uses_provider(self, mock_instrument, mock_depth_provider):
        decorator = Depth20Decorator(mock_instrument, mock_depth_provider)
        result = decorator.depth(levels=20)
        mock_depth_provider.depth.assert_called_once_with("RELIANCE", "NSE", 20)
        assert result is not None

    def test_depth_20_decorator(self, mock_instrument, mock_depth_provider):
        decorator = Depth20Decorator(mock_instrument, mock_depth_provider)
        result = decorator.depth_20()
        mock_depth_provider.depth.assert_called_once_with("RELIANCE", "NSE", 20)
        assert result is not None

    def test_depth_30_decorator(self, mock_instrument, mock_depth_provider):
        decorator = Depth30Decorator(mock_instrument, mock_depth_provider)
        result = decorator.depth_30()
        mock_depth_provider.depth.assert_called_once_with("RELIANCE", "NSE", 30)
        assert result is not None

    def test_depth_200_decorator(self, mock_instrument, mock_depth_provider):
        decorator = Depth200Decorator(mock_instrument, mock_depth_provider)
        result = decorator.depth_200()
        mock_depth_provider.depth.assert_called_once_with("RELIANCE", "NSE", 200)
        assert result is not None

    def test_depth_decorator_delegates_other_attrs(
        self,
        mock_instrument,
        mock_depth_provider,
    ):
        decorator = Depth20Decorator(mock_instrument, mock_depth_provider)
        assert decorator.symbol == "RELIANCE"
        assert decorator.composite_key == "NSE:RELIANCE"
        assert decorator.is_equity() is True

    def test_depth_decorator_supports_depth(self, mock_instrument, mock_depth_provider):
        decorator = Depth20Decorator(mock_instrument, mock_depth_provider)
        # Without capabilities, defaults to 5
        assert decorator.supports_depth(5) is True
        assert decorator.supports_depth(20) is False

    def test_depth_decorator_repr(self, mock_instrument, mock_depth_provider):
        decorator = Depth200Decorator(mock_instrument, mock_depth_provider)
        assert "Depth200Decorator" in repr(decorator)
        assert "NSE:RELIANCE" in repr(decorator)


# ── CachedDecorator ──────────────────────────────────────────────────────


class TestCachedDecorator:
    """CachedDecorator should cache quote/LTP within TTL."""

    def test_cached_quote_returns_value(self, mock_instrument: Instrument) -> None:
        decorator = CachedDecorator(mock_instrument)
        result = decorator.quote()
        assert result is not None

    def test_cached_quote_hits_cache(self, mock_instrument: Instrument) -> None:
        decorator = CachedDecorator(mock_instrument, ttl_seconds=10.0)
        # First call fetches from wrapped
        result1 = decorator.quote()

        # Second call should use cache (not call wrapped)
        mock_instrument._provider.quote.reset_mock()
        result2 = decorator.quote()
        assert mock_instrument._provider.quote.call_count == 0
        assert result1 == result2

    def test_cached_quote_expires(self, mock_instrument: Instrument) -> None:
        decorator = CachedDecorator(mock_instrument, ttl_seconds=0.01)
        # First call
        decorator.quote()
        mock_instrument._provider.quote.reset_mock()

        # Wait for expiry
        time.sleep(0.02)

        # Second call should fetch fresh
        decorator.quote()
        assert mock_instrument._provider.quote.call_count == 1

    def test_cached_ltp_returns_value(self, mock_instrument: Instrument) -> None:
        decorator = CachedDecorator(mock_instrument)
        result = decorator.ltp()
        assert result == Decimal("2500")

    def test_cached_ltp_hits_cache(self, mock_instrument: Instrument) -> None:
        decorator = CachedDecorator(mock_instrument, ttl_seconds=10.0)
        decorator.ltp()
        mock_instrument._provider.ltp.reset_mock()

        result = decorator.ltp()
        assert mock_instrument._provider.ltp.call_count == 0

    def test_invalidate_clears_cache(self, mock_instrument: Instrument) -> None:
        decorator = CachedDecorator(mock_instrument, ttl_seconds=10.0)
        decorator.quote()
        mock_instrument._provider.quote.reset_mock()

        decorator.invalidate()
        decorator.quote()
        assert mock_instrument._provider.quote.call_count == 1

    def test_cached_decorator_repr(self, mock_instrument: Instrument) -> None:
        decorator = CachedDecorator(mock_instrument)
        assert "CachedDecorator" in repr(decorator)


# ── LoggedDecorator ──────────────────────────────────────────────────────


class TestLoggedDecorator:
    """LoggedDecorator should log method calls."""

    def test_logged_quote_logs(self, mock_instrument: Instrument, caplog) -> None:
        caplog.set_level(logging.INFO)
        decorator = LoggedDecorator(mock_instrument)
        decorator.quote()
        assert any("logged: quote()" in rec.message for rec in caplog.records)

    def test_logged_ltp_logs(self, mock_instrument: Instrument, caplog) -> None:
        caplog.set_level(logging.INFO)
        decorator = LoggedDecorator(mock_instrument)
        decorator.ltp()
        assert any("logged: ltp()" in rec.message for rec in caplog.records)

    def test_logged_depth_logs(self, mock_instrument: Instrument, caplog) -> None:
        caplog.set_level(logging.INFO)
        decorator = LoggedDecorator(mock_instrument)
        decorator.depth(20)
        assert any("logged: depth(20)" in rec.message for rec in caplog.records)

    def test_logged_delegates_ltp_value(self, mock_instrument: Instrument) -> None:
        decorator = LoggedDecorator(mock_instrument)
        assert decorator.ltp() == Decimal("2500")

    def test_logged_decorator_repr(self, mock_instrument: Instrument) -> None:
        decorator = LoggedDecorator(mock_instrument)
        assert "LoggedDecorator" in repr(decorator)
        assert "NSE:RELIANCE" in repr(decorator)


# ── Composition Helpers ──────────────────────────────────────────────────


class TestWithDepth:
    """with_depth() should select correct decorator."""

    def test_with_depth_5_returns_instrument(self, mock_instrument: Instrument) -> None:
        result = with_depth(mock_instrument, levels=5)
        assert result is mock_instrument  # No wrapper needed

    def test_with_depth_20_returns_depth20(self, mock_instrument: Instrument) -> None:
        result = with_depth(mock_instrument, levels=20)
        assert isinstance(result, Depth20Decorator)

    def test_with_depth_30_returns_depth30(self, mock_instrument: Instrument) -> None:
        result = with_depth(mock_instrument, levels=30)
        assert isinstance(result, Depth30Decorator)

    def test_with_depth_200_returns_depth200(self, mock_instrument: Instrument) -> None:
        result = with_depth(mock_instrument, levels=200)
        assert isinstance(result, Depth200Decorator)

    def test_with_depth_raises_on_unsupported(self, mock_instrument: Instrument) -> None:
        with pytest.raises(ValueError, match="Unsupported depth levels"):
            with_depth(mock_instrument, levels=999)


class TestWithCache:
    """with_cache() should return CachedDecorator."""

    def test_with_cache_returns_cached(self, mock_instrument: Instrument) -> None:
        result = with_cache(mock_instrument)
        assert isinstance(result, CachedDecorator)

    def test_with_cache_custom_ttl(self, mock_instrument: Instrument) -> None:
        result = with_cache(mock_instrument, ttl_seconds=5.0)
        assert isinstance(result, CachedDecorator)
        assert result._ttl == 5.0


class TestWithLogging:
    """with_logging() should return LoggedDecorator."""

    def test_with_logging_returns_logged(self, mock_instrument: Instrument) -> None:
        result = with_logging(mock_instrument)
        assert isinstance(result, LoggedDecorator)


# ── Decorator Composition ────────────────────────────────────────────────


class TestDecoratorComposition:
    """Multiple decorators should stack correctly."""

    def test_compose_depth_then_cache(self, mock_instrument, mock_depth_provider):
        inst = CachedDecorator(
            Depth200Decorator(mock_instrument, mock_depth_provider),
        )
        # depth should use Depth200Decorator
        result = inst.depth(200)
        mock_depth_provider.depth.assert_called_once_with("RELIANCE", "NSE", 200)
        assert result is not None

        # quote should be cached
        inst.quote()
        mock_instrument._provider.quote.reset_mock()
        inst.quote()
        assert mock_instrument._provider.quote.call_count == 0

    def test_compose_all_three(self, mock_instrument, mock_depth_provider):
        inst = LoggedDecorator(
            CachedDecorator(
                Depth200Decorator(mock_instrument, mock_depth_provider),
            ),
        )
        assert inst.symbol == "RELIANCE"
        assert inst.composite_key == "NSE:RELIANCE"
        assert isinstance(inst._wrapped, CachedDecorator)
        assert isinstance(inst._wrapped._wrapped, Depth200Decorator)

    def test_compose_with_helpers(self, mock_instrument, mock_depth_provider):
        base = with_depth(mock_instrument, levels=200, depth_provider=mock_depth_provider)
        cached = with_cache(base, ttl_seconds=3.0)
        logged = with_logging(cached)

        assert isinstance(logged, LoggedDecorator)
        assert isinstance(logged._wrapped, CachedDecorator)
        assert isinstance(logged._wrapped._wrapped, Depth200Decorator)

    def test_composed_still_delegates_identity(self, mock_instrument, mock_depth_provider):
        inst = LoggedDecorator(
            CachedDecorator(Depth200Decorator(mock_instrument, mock_depth_provider)),
        )
        assert inst.symbol == "RELIANCE"
        assert inst.is_equity() is True
        assert inst.composite_key == "NSE:RELIANCE"
