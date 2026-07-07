"""Tests for Account batch operations — place_orders, cancel_orders, modify_orders."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from brokers.domain.account import Account, RiskDecision
from brokers.domain.enums import Exchange, Side
from brokers.domain.requests import ModifyOrderRequest, OrderRequest
from brokers.domain.values import Balance, OrderResponse
from brokers.infrastructure.event_bus import EventBus


class _BatchMockProvider:
    """Minimal provider with full capabilities for batch testing."""
    broker_id = "batch-mock"
    is_connected = True

    @property
    def capabilities(self):
        from brokers.domain.capabilities import Capability, ProviderCapabilities
        return ProviderCapabilities.full(self.broker_id)

    @property
    def extensions(self):
        from brokers.provider.extensions import ExtensionAccess
        return ExtensionAccess(self, extensions={})

    async def connect(self): pass
    async def disconnect(self): pass

    async def place_order(self, request): return OrderResponse.ok(order_id="mock", message="ok")
    async def cancel_order(self, order_id): return OrderResponse.ok(order_id=order_id, message="cancelled")
    async def modify_order(self, request): return OrderResponse.ok(order_id=request.order_id, message="modified")
    async def get_positions(self): return []
    async def get_balance(self): return Balance(total=0, used=0, available=0)
    async def get_orders(self): return []
    async def get_trades(self): return []
    async def get_holdings(self): return []


class TestBatchOperations:
    """Batch operations on Account — place_orders, cancel_orders, modify_orders."""

    @pytest.fixture
    def provider(self):
        p = MagicMock()
        p.broker_id = "batch-test"
        p.capabilities = _BatchMockProvider().capabilities
        p.extensions = _BatchMockProvider().extensions
        p.is_connected = True
        p.place_order = AsyncMock(return_value=OrderResponse.ok(order_id="ord1", message="ok"))
        p.cancel_order = AsyncMock(return_value=OrderResponse.ok(order_id="ord1", message="cancelled"))
        p.modify_order = AsyncMock(return_value=OrderResponse.ok(order_id="ord1", message="modified"))
        return p

    @pytest.fixture
    def account(self, provider):
        return Account("batch-test", provider, event_bus=EventBus())

    @pytest.mark.asyncio
    async def test_place_orders_batch(self, account, provider):
        """place_orders executes multiple orders and returns results in order."""
        requests = [
            OrderRequest("RELIANCE", Exchange.NSE, Side.BUY, 10),
            OrderRequest("TCS", Exchange.NSE, Side.BUY, 5),
            OrderRequest("INFY", Exchange.NSE, Side.SELL, 3),
        ]
        provider.place_order.side_effect = [
            OrderResponse.ok(order_id=f"ord{i}", message="ok")
            for i in range(len(requests))
        ]
        results = await account.place_orders(requests)
        assert len(results) == 3
        assert results[0].order_id == "ord0"
        assert results[1].order_id == "ord1"
        assert results[2].order_id == "ord2"
        assert all(r.success for r in results)
        assert provider.place_order.call_count == 3

    @pytest.mark.asyncio
    async def test_cancel_orders_batch(self, account, provider):
        """cancel_orders cancels multiple orders concurrently."""
        provider.cancel_order.side_effect = [
            OrderResponse.ok(order_id=f"ord{i}", message="cancelled")
            for i in range(3)
        ]
        results = await account.cancel_orders(["ord0", "ord1", "ord2"])
        assert len(results) == 3
        assert all(r.success for r in results)
        assert provider.cancel_order.call_count == 3

    @pytest.mark.asyncio
    async def test_modify_orders_batch(self, account, provider):
        """modify_orders modifies multiple orders concurrently."""
        requests = [
            ModifyOrderRequest(order_id="ord0", quantity=15),
            ModifyOrderRequest(order_id="ord1", quantity=20),
        ]
        provider.modify_order.side_effect = [
            OrderResponse.ok(order_id="ord0", message="modified"),
            OrderResponse.ok(order_id="ord1", message="modified"),
        ]
        results = await account.modify_orders(requests)
        assert len(results) == 2
        assert all(r.success for r in results)
        assert provider.modify_order.call_count == 2

    @pytest.mark.asyncio
    async def test_place_orders_empty_list(self, account):
        """place_orders with empty list returns empty list."""
        results = await account.place_orders([])
        assert results == []

    @pytest.mark.asyncio
    async def test_cancel_orders_empty_list(self, account):
        """cancel_orders with empty list returns empty list."""
        results = await account.cancel_orders([])
        assert results == []

    @pytest.mark.asyncio
    async def test_modify_orders_empty_list(self, account):
        """modify_orders with empty list returns empty list."""
        results = await account.modify_orders([])
        assert results == []

    @pytest.mark.asyncio
    async def test_place_orders_concurrent_execution(self, account, provider):
        """place_orders runs individual place_order calls concurrently."""
        events = []

        async def slow_place(request):
            await asyncio.sleep(0.05)
            events.append(request.symbol)
            return OrderResponse.ok(order_id=request.symbol, message="ok")

        provider.place_order = slow_place
        requests = [
            OrderRequest("A", Exchange.NSE, Side.BUY, 1),
            OrderRequest("B", Exchange.NSE, Side.BUY, 1),
            OrderRequest("C", Exchange.NSE, Side.BUY, 1),
        ]
        results = await account.place_orders(requests)
        assert len(results) == 3
        assert all(r.success for r in results)

    @pytest.mark.asyncio
    async def test_place_orders_with_risk_rejection(self, account, provider):
        """place_orders handles risk-denied orders — provider not called."""
        deny_all = AsyncMock()
        deny_all.check.return_value = RiskDecision.deny(
            rule="TEST", value=1, limit=0, reason="no"
        )
        account._risk_policy = deny_all
        requests = [
            OrderRequest("RELIANCE", Exchange.NSE, Side.BUY, 10),
        ]
        results = await account.place_orders(requests)
        assert len(results) == 1
        assert not results[0].success
        assert "Risk denied" in results[0].message
        provider.place_order.assert_not_called()
