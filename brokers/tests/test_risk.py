"""Tests for risk policy implementations.

Covers:
  - _NoLimitsPolicy (allows everything)
  - _MaxPositionPolicy (quantity + notional limits)
  - fail-open vs fail-closed behavior when LTP fetch fails
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from brokers.domain.account import RiskDecision
from brokers.domain.capabilities import Capability, ProviderCapabilities
from brokers.domain.enums import Exchange, OrderType, ProductType, Side
from brokers.domain.requests import OrderRequest
from brokers.risk import RiskPolicy


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_request(quantity: int = 10, **kwargs: Any) -> OrderRequest:
    return OrderRequest(
        symbol=kwargs.get("symbol", "RELIANCE"),
        exchange=kwargs.get("exchange", Exchange.NSE),
        side=kwargs.get("side", Side.BUY),
        quantity=quantity,
        order_type=kwargs.get("order_type", OrderType.MARKET),
        product_type=kwargs.get("product_type", ProductType.CNC),
    )


def _mock_provider(ltp: Decimal = Decimal("2500.00"), *, has_market_data: bool = True) -> Any:
    """Create a mock ExecutionProvider with optional MarketDataProvider."""
    provider = MagicMock()
    provider.get_ltp = AsyncMock(return_value=ltp)

    if has_market_data:
        caps = ProviderCapabilities(
            broker_id="test",
            supported=frozenset({Capability.ORDER_PLACEMENT, Capability.MARKET_DATA}),
            is_primary=True,
        )
    else:
        caps = ProviderCapabilities(
            broker_id="test",
            supported=frozenset({Capability.ORDER_PLACEMENT}),
            is_primary=True,
        )
    provider.capabilities = caps
    return provider


# ── NoLimitsPolicy ──────────────────────────────────────────────────────────


class TestNoLimitsPolicy:
    """RiskPolicy.no_limits() allows everything."""

    @pytest.mark.asyncio
    async def test_allows_any_order(self) -> None:
        policy = RiskPolicy.no_limits()
        request = _make_request(quantity=999_999)
        provider = _mock_provider()

        result = await policy.check(request, provider)

        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_does_not_call_provider(self) -> None:
        policy = RiskPolicy.no_limits()
        request = _make_request()
        provider = _mock_provider()

        await policy.check(request, provider)

        provider.get_ltp.assert_not_called()


# ── MaxPositionPolicy: quantity limit ───────────────────────────────────────


class TestMaxPositionQuantity:
    """Quantity gating."""

    @pytest.mark.asyncio
    async def test_within_limit_allowed(self) -> None:
        policy = RiskPolicy.max_position(max_quantity=100)
        request = _make_request(quantity=50)
        provider = _mock_provider(has_market_data=False)

        result = await policy.check(request, provider)

        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_at_limit_allowed(self) -> None:
        policy = RiskPolicy.max_position(max_quantity=100)
        request = _make_request(quantity=100)
        provider = _mock_provider(has_market_data=False)

        result = await policy.check(request, provider)

        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_over_limit_denied(self) -> None:
        policy = RiskPolicy.max_position(max_quantity=100)
        request = _make_request(quantity=101)
        provider = _mock_provider(has_market_data=False)

        result = await policy.check(request, provider)

        assert result.allowed is False
        assert result.rule == "MAX_QUANTITY"
        assert result.value == Decimal("101")
        assert result.limit == Decimal("100")


# ── MaxPositionPolicy: notional limit ───────────────────────────────────────


class TestMaxPositionNotional:
    """Notional value gating (LTP * quantity)."""

    @pytest.mark.asyncio
    async def test_within_notional_allowed(self) -> None:
        # LTP=2500, qty=10 → notional=25000 < limit=100000
        policy = RiskPolicy.max_position(max_quantity=1000, max_notional=Decimal("100000"))
        request = _make_request(quantity=10)
        provider = _mock_provider(ltp=Decimal("2500.00"))

        result = await policy.check(request, provider)

        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_over_notional_denied(self) -> None:
        # LTP=2500, qty=100 → notional=250000 > limit=100000
        policy = RiskPolicy.max_position(max_quantity=1000, max_notional=Decimal("100000"))
        request = _make_request(quantity=100)
        provider = _mock_provider(ltp=Decimal("2500.00"))

        result = await policy.check(request, provider)

        assert result.allowed is False
        assert result.rule == "MAX_NOTIONAL"
        assert result.value == Decimal("250000")
        assert result.limit == Decimal("100000")

    @pytest.mark.asyncio
    async def test_no_market_data_capability_allows(self) -> None:
        """If provider can't do market data, notional check is skipped."""
        policy = RiskPolicy.max_position(max_quantity=1000, max_notional=Decimal("100"))
        request = _make_request(quantity=10)
        provider = _mock_provider(has_market_data=False)

        result = await policy.check(request, provider)

        assert result.allowed is True


# ── MaxPositionPolicy: fail-open / fail-closed ─────────────────────────────


class TestMaxPositionFailMode:
    """When LTP fetch raises, fail-open allows; fail-closed denies."""

    @pytest.mark.asyncio
    async def test_fail_closed_denies_on_ltp_error(self) -> None:
        policy = RiskPolicy.max_position(
            max_quantity=1000,
            max_notional=Decimal("100000"),
            fail_open=False,
        )
        request = _make_request(quantity=10)
        provider = _mock_provider()
        provider.get_ltp.side_effect = RuntimeError("network error")

        result = await policy.check(request, provider)

        assert result.allowed is False
        assert result.rule == "MAX_NOTIONAL_CHECK_FAILED"

    @pytest.mark.asyncio
    async def test_fail_open_allows_on_ltp_error(self) -> None:
        policy = RiskPolicy.max_position(
            max_quantity=1000,
            max_notional=Decimal("100000"),
            fail_open=True,
        )
        request = _make_request(quantity=10)
        provider = _mock_provider()
        provider.get_ltp.side_effect = RuntimeError("network error")

        result = await policy.check(request, provider)

        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_default_is_fail_closed(self) -> None:
        """Default fail_open=False (safer)."""
        policy = RiskPolicy.max_position(
            max_quantity=1000,
            max_notional=Decimal("100000"),
        )
        request = _make_request(quantity=10)
        provider = _mock_provider()
        provider.get_ltp.side_effect = RuntimeError("boom")

        result = await policy.check(request, provider)

        assert result.allowed is False
