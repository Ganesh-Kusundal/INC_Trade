"""Tests for InstrumentFactory provider injection (Phase 1).

Covers:
- Factory injects ``_depth_provider`` and ``_order_provider``
- ``apply_depth`` triggers decorator wrapping
- ``buy()`` / ``sell()`` delegation on Instrument
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from inc_trade.market.depth_decorators import (
    Depth20Decorator,
    Depth30Decorator,
    Depth200Decorator,
)
from inc_trade.market.factory import InstrumentFactory


@pytest.fixture
def mock_provider() -> MagicMock:
    """A provider that supports quote, depth, and order operations."""
    provider = MagicMock()
    provider.quote.return_value = {"symbol": "RELIANCE", "ltp": Decimal("2500")}
    provider.ltp.return_value = Decimal("2500")
    provider.depth.return_value = {"bids": [], "asks": []}
    provider.place_order.return_value = {"order_id": "ORD001", "success": True}
    return provider


class TestFactoryProviderInjection:
    """Factory should wire providers correctly."""

    def test_factory_injects_provider(self, mock_provider) -> None:
        inst = InstrumentFactory.create(
            symbol="RELIANCE",
            exchange="NSE",
            provider=mock_provider,
        )
        assert inst._provider is mock_provider

    def test_factory_injects_depth_provider(self, mock_provider) -> None:
        depth_provider = MagicMock()
        inst = InstrumentFactory.create(
            symbol="RELIANCE",
            exchange="NSE",
            provider=mock_provider,
            depth_provider=depth_provider,
        )
        assert inst._depth_provider is depth_provider

    def test_factory_depth_provider_falls_back_to_provider(self, mock_provider) -> None:
        inst = InstrumentFactory.create(
            symbol="RELIANCE",
            exchange="NSE",
            provider=mock_provider,
        )
        assert inst._depth_provider is mock_provider

    def test_factory_injects_order_provider(self, mock_provider) -> None:
        order_provider = MagicMock()
        inst = InstrumentFactory.create(
            symbol="RELIANCE",
            exchange="NSE",
            provider=mock_provider,
            order_provider=order_provider,
        )
        assert inst._order_provider is order_provider

    def test_factory_order_provider_falls_back_to_provider(self, mock_provider) -> None:
        inst = InstrumentFactory.create(
            symbol="RELIANCE",
            exchange="NSE",
            provider=mock_provider,
        )
        assert inst._order_provider is mock_provider

    def test_factory_injects_streaming_provider(self, mock_provider) -> None:
        sp = MagicMock()
        inst = InstrumentFactory.create(
            symbol="RELIANCE",
            exchange="NSE",
            provider=mock_provider,
            streaming_provider=sp,
        )
        assert inst._streaming_provider is sp


class TestFactoryApplyDepth:
    """Factory's apply_depth should auto-apply depth decorators."""

    def test_apply_depth_20_wraps_with_depth20(self, mock_provider) -> None:
        inst = InstrumentFactory.create(
            symbol="RELIANCE",
            exchange="NSE",
            provider=mock_provider,
            apply_depth=20,
        )
        assert isinstance(inst, Depth20Decorator)

    def test_apply_depth_30_wraps_with_depth30(self, mock_provider) -> None:
        inst = InstrumentFactory.create(
            symbol="RELIANCE",
            exchange="NSE",
            provider=mock_provider,
            apply_depth=30,
        )
        assert isinstance(inst, Depth30Decorator)

    def test_apply_depth_200_wraps_with_depth200(self, mock_provider) -> None:
        inst = InstrumentFactory.create(
            symbol="RELIANCE",
            exchange="NSE",
            provider=mock_provider,
            apply_depth=200,
        )
        assert isinstance(inst, Depth200Decorator)

    def test_apply_depth_0_no_wrapper(self, mock_provider) -> None:
        inst = InstrumentFactory.create(
            symbol="RELIANCE",
            exchange="NSE",
            provider=mock_provider,
            apply_depth=0,
        )
        from inc_trade.market.types.equity import Equity

        assert isinstance(inst, Equity)
        assert not isinstance(inst, Depth20Decorator)

    def test_apply_depth_omitted_no_wrapper(self, mock_provider) -> None:
        inst = InstrumentFactory.create(
            symbol="RELIANCE",
            exchange="NSE",
            provider=mock_provider,
        )
        from inc_trade.market.types.equity import Equity

        assert isinstance(inst, Equity)
        assert not isinstance(inst, Depth20Decorator)

    def test_apply_depth_delegates_quote(self, mock_provider) -> None:
        inst = InstrumentFactory.create(
            symbol="RELIANCE",
            exchange="NSE",
            provider=mock_provider,
            apply_depth=200,
        )
        result = inst.quote()
        assert result is not None
        assert result["symbol"] == "RELIANCE"

    def test_apply_depth_calls_depth_provider(self, mock_provider) -> None:
        dp = MagicMock()
        dp.depth.return_value = {"bids": [], "asks": []}
        inst = InstrumentFactory.create(
            symbol="RELIANCE",
            exchange="NSE",
            provider=mock_provider,
            depth_provider=dp,
            apply_depth=200,
        )
        inst.depth(200)
        dp.depth.assert_called_once_with("RELIANCE", "NSE", 200)


class TestInstrumentBuySell:
    """Instrument.buy() and .sell() should delegate to order provider."""

    def test_buy_delegates_to_order_provider(self, mock_provider) -> None:
        inst = InstrumentFactory.create(
            symbol="RELIANCE",
            exchange="NSE",
            provider=mock_provider,
        )
        result = inst.buy(quantity=10)
        mock_provider.place_order.assert_called_once()
        call_kwargs = mock_provider.place_order.call_args[1]
        assert call_kwargs["symbol"] == "RELIANCE"
        assert call_kwargs["side"] == "BUY"
        assert call_kwargs["quantity"] == 10
        assert result == {"order_id": "ORD001", "success": True}

    def test_buy_delegates_to_dedicated_order_provider(self, mock_provider) -> None:
        order_provider = MagicMock()
        order_provider.place_order.return_value = {"order_id": "ORD002", "success": True}
        inst = InstrumentFactory.create(
            symbol="RELIANCE",
            exchange="NSE",
            provider=mock_provider,
            order_provider=order_provider,
        )
        inst.buy(quantity=5)
        order_provider.place_order.assert_called_once()
        mock_provider.place_order.assert_not_called()

    def test_sell_delegates_to_order_provider(self, mock_provider) -> None:
        inst = InstrumentFactory.create(
            symbol="RELIANCE",
            exchange="NSE",
            provider=mock_provider,
        )
        result = inst.sell(quantity=10)
        mock_provider.place_order.assert_called_once()
        call_kwargs = mock_provider.place_order.call_args[1]
        assert call_kwargs["symbol"] == "RELIANCE"
        assert call_kwargs["side"] == "SELL"
        assert call_kwargs["quantity"] == 10
        assert result == {"order_id": "ORD001", "success": True}

    def test_buy_raises_without_provider(self) -> None:
        inst = InstrumentFactory.create(
            symbol="RELIANCE",
            exchange="NSE",
        )
        with pytest.raises(RuntimeError, match="No order provider configured"):
            inst.buy(quantity=10)

    def test_buy_custom_order_type(self, mock_provider) -> None:
        from inc_trade.domain.enums import OrderType

        inst = InstrumentFactory.create(
            symbol="RELIANCE",
            exchange="NSE",
            provider=mock_provider,
        )
        inst.buy(quantity=10, order_type=OrderType.LIMIT, price=Decimal("2500"))
        call_kwargs = mock_provider.place_order.call_args[1]
        assert call_kwargs["price"] == Decimal("2500")

    def test_depth_uses_depth_provider_before_general(self, mock_provider) -> None:
        dp = MagicMock()
        dp.depth.return_value = {"bids": [], "asks": []}
        inst = InstrumentFactory.create(
            symbol="RELIANCE",
            exchange="NSE",
            provider=mock_provider,
            depth_provider=dp,
        )
        inst.depth(20)
        dp.depth.assert_called_once_with("RELIANCE", "NSE", 20)
        mock_provider.depth.assert_not_called()

    def test_factory_creates_option_with_providers(self, mock_provider) -> None:
        inst = InstrumentFactory.create(
            symbol="NIFTY",
            exchange="NFO",
            expiry=datetime(2025, 1, 30, tzinfo=UTC),
            strike=Decimal("18000"),
            option_type="CE",
            lot_size=50,
            provider=mock_provider,
        )
        assert inst.is_option() is True
        assert inst._provider is mock_provider
        assert inst._order_provider is mock_provider

    def test_factory_creates_future_with_providers(self, mock_provider) -> None:
        inst = InstrumentFactory.create(
            symbol="RELIANCE",
            exchange="NFO",
            expiry=datetime(2025, 6, 26, tzinfo=UTC),
            lot_size=1,
            provider=mock_provider,
        )
        # Note: Future's underlying/contract_size are class-level annotations,
        # not dataclass fields. The factory extracts underlying from symbol via regex.
        assert inst.is_future() is True
        assert inst._provider is mock_provider
        assert inst._order_provider is mock_provider

    def test_factory_creates_index_with_providers(self, mock_provider) -> None:
        inst = InstrumentFactory.create(
            symbol="NIFTY",
            exchange="NSE",
            isin="",
            provider=mock_provider,
        )
        assert inst._provider is mock_provider
