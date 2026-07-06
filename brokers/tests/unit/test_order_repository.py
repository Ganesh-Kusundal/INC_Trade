"""Tests for OrderRepository — thread-safe in-memory order store."""

from __future__ import annotations

from decimal import Decimal

from inc_trade.domain.entities import Order
from inc_trade.domain.enums import OrderStatus, Side
from inc_trade.trading.order_repository import OrderRepository


class TestOrderRepository:
    """Comprehensive test suite for OrderRepository."""

    def _make_order(
        self,
        order_id: str = "ORD-001",
        symbol: str = "RELIANCE",
        status: OrderStatus = OrderStatus.PENDING,
        filled_quantity: int = 0,
        **kwargs,
    ) -> Order:
        return Order(
            order_id=order_id,
            symbol=symbol,
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            status=status,
            price=Decimal("2500"),
            filled_quantity=filled_quantity,
            **kwargs,
        )

    # ── Save & Get ─────────────────────────────────────────────────────

    def test_save_and_get(self):
        """Round-trip: save order then retrieve by ID."""
        repo = OrderRepository()
        order = self._make_order()
        repo.save(order, account_id="dhan/default")

        retrieved = repo.get("ORD-001")
        assert retrieved is not None
        assert retrieved.order_id == "ORD-001"
        assert retrieved.symbol == "RELIANCE"
        assert retrieved.side is Side.BUY

    def test_get_returns_none_for_missing(self):
        """Unknown order_id returns None (not KeyError)."""
        repo = OrderRepository()
        result = repo.get("NONEXISTENT")
        assert result is None

    def test_contains_checks_membership(self):
        """__contains__ works for order IDs."""
        repo = OrderRepository()
        order = self._make_order()
        repo.save(order)
        assert "ORD-001" in repo
        assert "NONEXISTENT" not in repo

    # ── Update Status ──────────────────────────────────────────────────

    def test_update_status(self):
        """Status can be updated and returns updated Order."""
        repo = OrderRepository()
        repo.save(self._make_order())
        updated = repo.update_status(
            "ORD-001",
            new_status=OrderStatus.OPEN,
            filled_quantity=5,
            message="Order opened",
        )
        assert updated is not None
        assert updated.status is OrderStatus.OPEN
        assert updated.filled_quantity == 5
        assert updated.message == "Order opened"

    def test_update_status_returns_none_for_unknown(self):
        """Updating unknown order_id returns None."""
        repo = OrderRepository()
        result = repo.update_status("NONEXISTENT", OrderStatus.FILLED)
        assert result is None

    def test_update_status_preserves_original_fields(self):
        """Unchanged fields remain intact after status update."""
        repo = OrderRepository()
        repo.save(self._make_order(correlation_id="corr-123"))
        updated = repo.update_status("ORD-001", OrderStatus.FILLED, filled_quantity=10)
        assert updated is not None
        assert updated.symbol == "RELIANCE"
        assert updated.quantity == 10
        assert updated.correlation_id == "corr-123"
        assert updated.price == Decimal("2500")

    # ── Account Queries ────────────────────────────────────────────────

    def test_get_by_account(self):
        """Orders can be queried by account_id."""
        repo = OrderRepository()
        repo.save(self._make_order("ORD-001"), account_id="dhan/default")
        repo.save(self._make_order("ORD-002"), account_id="dhan/default")
        repo.save(self._make_order("ORD-003"), account_id="upstox/default")

        dhan_orders = repo.get_by_account("dhan/default")
        assert len(dhan_orders) == 2

        upstox_orders = repo.get_by_account("upstox/default")
        assert len(upstox_orders) == 1

    def test_get_by_account_empty_for_unknown(self):
        """Unknown account returns empty list (not error)."""
        repo = OrderRepository()
        result = repo.get_by_account("unknown/account")
        assert result == []

    # ── Active Filtering ───────────────────────────────────────────────

    def test_get_active_filters_terminal_states(self):
        """Active orders exclude FILLED, CANCELLED, REJECTED, EXPIRED."""
        repo = OrderRepository()
        repo.save(self._make_order("ORD-001", status=OrderStatus.OPEN), account_id="dhan/default")
        repo.save(
            self._make_order("ORD-002", status=OrderStatus.FILLED),
            account_id="dhan/default",
        )
        repo.save(
            self._make_order("ORD-003", status=OrderStatus.CANCELLED),
            account_id="dhan/default",
        )
        repo.save(
            self._make_order("ORD-004", status=OrderStatus.PARTIALLY_FILLED),
            account_id="upstox/default",
        )

        all_active = repo.get_active()
        assert len(all_active) == 2
        active_ids = {o.order_id for o in all_active}
        assert "ORD-001" in active_ids
        assert "ORD-004" in active_ids

    def test_get_active_by_account(self):
        """Active orders can be filtered by account."""
        repo = OrderRepository()
        repo.save(self._make_order("ORD-001", status=OrderStatus.OPEN), account_id="dhan/default")
        repo.save(
            self._make_order("ORD-002", status=OrderStatus.FILLED),
            account_id="dhan/default",
        )
        repo.save(self._make_order("ORD-003", status=OrderStatus.OPEN), account_id="upstox/default")

        dhan_active = repo.get_active(account_id="dhan/default")
        assert len(dhan_active) == 1
        assert dhan_active[0].order_id == "ORD-001"

    # ── Count & Clear ──────────────────────────────────────────────────

    def test_count(self):
        """count returns total number of stored orders."""
        repo = OrderRepository()
        assert repo.count() == 0
        repo.save(self._make_order("ORD-001"))
        assert repo.count() == 1
        repo.save(self._make_order("ORD-002"))
        assert repo.count() == 2

    def test_get_all(self):
        """get_all returns all stored orders."""
        repo = OrderRepository()
        repo.save(self._make_order("ORD-001"))
        repo.save(self._make_order("ORD-002"))
        all_orders = repo.get_all()
        assert len(all_orders) == 2

    def test_clear(self):
        """clear removes all orders."""
        repo = OrderRepository()
        repo.save(self._make_order("ORD-001"))
        repo.save(self._make_order("ORD-002"))
        repo.clear()
        assert repo.count() == 0
        assert repo.get("ORD-001") is None

    # ── Thread Safety ──────────────────────────────────────────────────

    def test_thread_safety(self):
        """Concurrent saves from multiple threads don't corrupt state."""
        import threading

        repo = OrderRepository()
        errors = []

        def save_order(idx: int) -> None:
            try:
                order = self._make_order(order_id=f"ORD-{idx:04d}")
                repo.save(order, account_id="dhan/default")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=save_order, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert len(errors) == 0
        assert repo.count() == 50
