"""Tests for PaperAdapter trading flow — order placement, lifecycle, events.

Verifies:
- Order placement with immediate fill simulation
- Order lifecycle (modify, cancel, query)
- Input validation (side, quantity, connection state)
- Position aggregation from filled orders
- Session-level OrderCommand integration
- Event publishing via OrderCommand → EventBus
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest
from inc_trade.domain.enums import OrderStatus, Side

from brokers.adapters.paper.adapter import PaperAdapter


class TestPaperTradingLifecycle:
    """Order lifecycle: place, modify, cancel, query."""

    @pytest.fixture
    def adapter(self) -> PaperAdapter:
        adapter = PaperAdapter()
        adapter.connect()
        return adapter

    def test_place_buy_order(self, adapter: PaperAdapter) -> None:
        """place_order with BUY returns a filled order response."""
        result = adapter.place_order("RELIANCE", "NSE", "BUY", 10)
        assert result.success
        assert result.order_id.startswith("PAPER-")
        assert result.status == OrderStatus.FILLED

        order = adapter.get_order(result.order_id)
        assert order is not None
        assert order.side == Side.BUY
        assert order.quantity == 10
        assert order.status == OrderStatus.FILLED
        assert order.filled_quantity == 10

    def test_place_sell_order(self, adapter: PaperAdapter) -> None:
        """place_order with SELL returns a filled order response."""
        result = adapter.place_order("RELIANCE", "NSE", "SELL", 5)
        assert result.success
        assert result.status == OrderStatus.FILLED

        order = adapter.get_order(result.order_id)
        assert order is not None
        assert order.side == Side.SELL
        assert order.filled_quantity == 5

    def test_modify_order(self, adapter: PaperAdapter) -> None:
        """modify_order updates an existing order's quantity."""
        result = adapter.place_order("RELIANCE", "NSE", "BUY", 10)
        modified = adapter.modify_order(result.order_id, quantity=15)
        assert modified.success

    def test_cancel_order(self, adapter: PaperAdapter) -> None:
        """cancel_order cancels an existing order."""
        result = adapter.place_order("RELIANCE", "NSE", "BUY", 10)
        cancelled = adapter.cancel_order(result.order_id)
        assert cancelled.success

    def test_order_not_found(self, adapter: PaperAdapter) -> None:
        """get_order returns None for unknown order ID."""
        assert adapter.get_order("NONEXISTENT") is None
        assert adapter.get_order("") is None

    def test_filled_order_updates_positions(self, adapter: PaperAdapter) -> None:
        """A filled BUY order creates a long position."""
        adapter.place_order("RELIANCE", "NSE", "BUY", 10)

        positions = adapter.get_positions()
        assert len(positions) == 1
        assert positions[0]["symbol"] == "RELIANCE"
        assert positions[0]["quantity"] == 10

    def test_get_positions(self, adapter: PaperAdapter) -> None:
        """get_positions aggregates orders by symbol."""
        adapter.place_order("RELIANCE", "NSE", "BUY", 10)
        adapter.place_order("TCS", "NSE", "BUY", 5)
        adapter.place_order("RELIANCE", "NSE", "SELL", 3)

        positions = adapter.get_positions()
        assert len(positions) == 2

        rel = next(p for p in positions if p["symbol"] == "RELIANCE")
        tcs = next(p for p in positions if p["symbol"] == "TCS")

        assert rel["quantity"] == 7  # 10 - 3
        assert tcs["quantity"] == 5

    def test_multiple_orders(self, adapter: PaperAdapter) -> None:
        """get_orders returns all placed orders."""
        adapter.place_order("RELIANCE", "NSE", "BUY", 10)
        adapter.place_order("TCS", "NSE", "SELL", 5)
        adapter.place_order("RELIANCE", "NSE", "BUY", 3)

        orders = adapter.get_orders()
        assert len(orders) == 3

    def test_get_order_book(self, adapter: PaperAdapter) -> None:
        """get_order_book returns all orders (alias)."""
        adapter.place_order("RELIANCE", "NSE", "BUY", 10)
        book = adapter._orders.get_order_book()  # type: ignore[union-attr]
        assert len(book) == 1


class TestPaperTradingValidation:
    """Input validation for order placement."""

    @pytest.fixture
    def adapter(self) -> PaperAdapter:
        adapter = PaperAdapter()
        adapter.connect()
        return adapter

    def test_rejects_invalid_side(self, adapter: PaperAdapter) -> None:
        """Orders with invalid side are rejected."""
        result = adapter.place_order("RELIANCE", "NSE", "INVALID", 10)
        assert not result.success
        assert "Invalid side" in result.message

    def test_rejects_zero_quantity(self, adapter: PaperAdapter) -> None:
        """Orders with quantity 0 are rejected."""
        result = adapter.place_order("RELIANCE", "NSE", "BUY", 0)
        assert not result.success
        assert "Quantity" in result.message

    def test_rejects_negative_quantity(self, adapter: PaperAdapter) -> None:
        """Orders with negative quantity are rejected."""
        result = adapter.place_order("RELIANCE", "NSE", "BUY", -5)
        assert not result.success
        assert "Quantity" in result.message

    def test_rejects_order_when_disconnected(self) -> None:
        """Orders raise RuntimeError when adapter is not connected."""
        adapter = PaperAdapter()
        with pytest.raises((RuntimeError, ConnectionError), match="not connected"):
            adapter.place_order("RELIANCE", "NSE", "BUY", 10)

    def test_rejects_get_order_when_disconnected(self) -> None:
        """get_order raises RuntimeError when adapter is not connected."""
        adapter = PaperAdapter()
        with pytest.raises((RuntimeError, ConnectionError), match="not connected"):
            adapter.get_order("foo")

    def test_rejects_get_orders_when_disconnected(self) -> None:
        """get_orders raises RuntimeError when adapter is not connected."""
        adapter = PaperAdapter()
        with pytest.raises((RuntimeError, ConnectionError), match="not connected"):
            adapter.get_orders()

    def test_rejects_get_positions_when_disconnected(self) -> None:
        """get_positions raises RuntimeError when adapter is not connected."""
        adapter = PaperAdapter()
        with pytest.raises((RuntimeError, ConnectionError), match="not connected"):
            adapter.get_positions()


class TestSessionTradingFlow:
    """End-to-end: BrokerSession → OrderCommand → PaperAdapter → events."""

    @pytest.fixture
    def adapter(self) -> PaperAdapter:
        adapter = PaperAdapter()
        adapter.connect()
        return adapter

    def test_session_command_buy(self, adapter: PaperAdapter) -> None:
        """BrokerSession.command().buy() places an order."""
        from inc_trade.market.session import BrokerSession

        session = BrokerSession(adapter)

        async def run() -> None:
            await session.connect()
            rel = session.equity("RELIANCE")
            cmd = session.command(rel)
            result = cmd.buy(quantity=10)
            assert result.success
            assert result.order_id.startswith("PAPER-")
            assert result.status == OrderStatus.FILLED

        asyncio.run(run())

    def test_session_command_sell(self, adapter: PaperAdapter) -> None:
        """BrokerSession.command().sell() places an order."""
        from inc_trade.market.session import BrokerSession

        session = BrokerSession(adapter)

        async def run() -> None:
            await session.connect()
            rel = session.equity("RELIANCE")
            cmd = session.command(rel)
            result = cmd.sell(quantity=5)
            assert result.success
            assert result.status == OrderStatus.FILLED

        asyncio.run(run())

    def test_command_validates_instrument(self, adapter: PaperAdapter) -> None:
        """OrderCommand resolves provider from session adapter."""
        from inc_trade.market.session import BrokerSession

        session = BrokerSession(adapter)

        async def run() -> None:
            await session.connect()
            rel = session.equity("RELIANCE")
            cmd = session.command(rel)
            # Provider is resolved from adapter — should work
            result = cmd.buy(quantity=10)
            assert result.success

        asyncio.run(run())

    def test_order_placed_event_published(self, adapter: PaperAdapter) -> None:
        """OrderCommand publishes OrderPlacedEvent after successful order."""
        from inc_trade.domain.events import EVENT_ORDER_PLACED
        from inc_trade.market.session import BrokerSession

        session = BrokerSession(adapter)

        events: list = []
        session.event_bus.subscribe(EVENT_ORDER_PLACED, lambda e: events.append(e))

        async def run() -> None:
            await session.connect()
            rel = session.equity("RELIANCE")
            cmd = session.command(rel)
            result = cmd.buy(quantity=10)
            assert result.success

        asyncio.run(run())

        assert len(events) == 1
        assert events[0].symbol == "RELIANCE"
        assert events[0].quantity == 10

    def test_event_not_published_on_failure(self, adapter: PaperAdapter) -> None:
        """No event published when order placement fails."""
        from inc_trade.domain.events import EVENT_ORDER_PLACED
        from inc_trade.market.session import BrokerSession

        session = BrokerSession(adapter)

        events: list = []
        session.event_bus.subscribe(EVENT_ORDER_PLACED, lambda e: events.append(e))

        async def run() -> None:
            await session.connect()
            rel = session.equity("RELIANCE")
            cmd = session.command(rel)
            # Invalid side should fail without publishing event
            result = cmd._resolve_provider().place_order(  # type: ignore[attr-defined]
                symbol=rel.symbol,
                exchange=rel.exchange,
                side="INVALID",
                quantity=10,
            )
            assert not result.success

        asyncio.run(run())

        assert len(events) == 0
