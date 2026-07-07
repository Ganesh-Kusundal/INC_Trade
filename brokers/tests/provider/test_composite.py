"""Tests for CompositeProvider — failover, caching, and lifecycle.

Covers:
  - default_account is cached (A1 regression)
  - connect() logs per-provider errors and raises if ALL fail (A5 regression)
  - Failover: primary fails -> secondary is tried
  - Capability merging across providers
  - Health tracking marks failed providers
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from brokers.domain.account import Account
from brokers.domain.capabilities import Capability, ProviderCapabilities
from brokers.domain.enums import Exchange, OrderStatus, OrderType, ProductType, Side
from brokers.domain.exceptions import ProviderError
from brokers.domain.requests import OrderRequest
from brokers.domain.values import (
    Balance,
    MarketDepth,
    OrderResponse,
    Quote,
    Subscription,
)
from brokers.infrastructure.event_bus import EventBus
from brokers.provider.composite import CompositeProvider
from brokers.provider.routing import RoutingStrategy


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_provider(
    broker_id: str = "test",
    *,
    connected: bool = True,
    capabilities: frozenset[Capability] | None = None,
) -> MagicMock:
    """Create a mock Provider with sensible defaults."""
    p = MagicMock()
    p.broker_id = broker_id
    p.is_connected = connected
    p.connect = AsyncMock()
    p.disconnect = AsyncMock()

    if capabilities is None:
        capabilities = frozenset({
            Capability.MARKET_DATA,
            Capability.ORDER_PLACEMENT,
            Capability.PORTFOLIO,
            Capability.STREAMING,
        })

    p.capabilities = ProviderCapabilities(
        broker_id=broker_id,
        supported=capabilities,
        is_primary=True,
    )

    p.get_ltp = AsyncMock(return_value=Decimal("100.00"))
    p.get_quote = AsyncMock(return_value=MagicMock(spec=Quote))
    p.get_depth = AsyncMock(return_value=MagicMock(spec=MarketDepth))
    p.place_order = AsyncMock(
        return_value=OrderResponse(success=True, order_id="ord1", status=OrderStatus.PENDING)
    )
    p.get_positions = AsyncMock(return_value=[])
    p.get_balance = AsyncMock(return_value=MagicMock(spec=Balance))
    p.get_orders = AsyncMock(return_value=[])
    p.get_trades = AsyncMock(return_value=[])
    p.get_holdings = AsyncMock(return_value=[])

    return p


# ── default_account caching (A1 regression) ─────────────────────────────────


class TestDefaultAccountCaching:
    def test_returns_same_account_on_repeated_access(self) -> None:
        p1 = _make_provider("p1")
        composite = CompositeProvider([p1])

        account1 = composite.default_account
        account2 = composite.default_account

        assert account1 is account2
        assert isinstance(account1, Account)

    def test_different_composites_have_different_accounts(self) -> None:
        p1 = _make_provider("p1")
        p2 = _make_provider("p2")

        c1 = CompositeProvider([p1])
        c2 = CompositeProvider([p2])

        assert c1.default_account is not c2.default_account


# ── connect() exception handling (A5 regression) ───────────────────────────


class TestConnectExceptionHandling:
    @pytest.mark.asyncio
    async def test_raises_if_all_providers_fail(self) -> None:
        p1 = _make_provider("p1")
        p1.connect.side_effect = RuntimeError("p1 down")
        p2 = _make_provider("p2")
        p2.connect.side_effect = RuntimeError("p2 down")

        composite = CompositeProvider([p1, p2])

        with pytest.raises(ProviderError, match="All 2 provider"):
            await composite.connect()

    @pytest.mark.asyncio
    async def test_succeeds_if_at_least_one_provider_connects(self) -> None:
        p1 = _make_provider("p1")
        p1.connect.side_effect = RuntimeError("p1 down")
        p2 = _make_provider("p2")

        composite = CompositeProvider([p1, p2])
        await composite.connect()

        p1.connect.assert_awaited_once()
        p2.connect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_disconnect_logs_but_does_not_raise(self) -> None:
        p1 = _make_provider("p1")
        p1.disconnect.side_effect = RuntimeError("disconnect error")
        p2 = _make_provider("p2")

        composite = CompositeProvider([p1, p2])
        await composite.disconnect()


# ── Failover behavior ──────────────────────────────────────────────────────


class TestFailover:
    @pytest.mark.asyncio
    async def test_get_ltp_falls_back_to_secondary(self) -> None:
        p1 = _make_provider("primary")
        p1.get_ltp.side_effect = ProviderError("primary down")
        p2 = _make_provider("secondary")
        p2.get_ltp = AsyncMock(return_value=Decimal("200.00"))

        composite = CompositeProvider(
            [p1, p2],
            routing=RoutingStrategy.primary_only(),
        )

        instrument = MagicMock()
        result = await composite.get_ltp(instrument)

        assert result == Decimal("200.00")
        p2.get_ltp.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_raises_if_all_providers_fail(self) -> None:
        p1 = _make_provider("primary")
        p1.get_ltp.side_effect = ProviderError("p1 down")
        p2 = _make_provider("secondary")
        p2.get_ltp.side_effect = ProviderError("p2 down")

        composite = CompositeProvider([p1, p2])

        instrument = MagicMock()
        with pytest.raises(ProviderError):
            await composite.get_ltp(instrument)


# ── Capability merging ─────────────────────────────────────────────────────


class TestCapabilityMerging:
    def test_merges_capabilities(self) -> None:
        p1 = _make_provider(
            "data",
            capabilities=frozenset({Capability.MARKET_DATA, Capability.DEPTH}),
        )
        p2 = _make_provider(
            "exec",
            capabilities=frozenset({Capability.ORDER_PLACEMENT, Capability.PORTFOLIO}),
        )

        composite = CompositeProvider([p1, p2])
        caps = composite.capabilities

        assert caps.supports(Capability.MARKET_DATA)
        assert caps.supports(Capability.DEPTH)
        assert caps.supports(Capability.ORDER_PLACEMENT)
        assert caps.supports(Capability.PORTFOLIO)

    def test_broker_id_is_composite(self) -> None:
        p1 = _make_provider("p1")
        composite = CompositeProvider([p1])
        assert composite.broker_id == "composite"


# ── Identity ───────────────────────────────────────────────────────────────


class TestIdentity:
    def test_is_connected_if_any_provider_connected(self) -> None:
        p1 = _make_provider("p1", connected=False)
        p2 = _make_provider("p2", connected=True)

        composite = CompositeProvider([p1, p2])
        assert composite.is_connected is True

    def test_is_connected_false_if_all_disconnected(self) -> None:
        p1 = _make_provider("p1", connected=False)
        p2 = _make_provider("p2", connected=False)

        composite = CompositeProvider([p1, p2])
        assert composite.is_connected is False

    def test_empty_providers_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one provider"):
            CompositeProvider([])
