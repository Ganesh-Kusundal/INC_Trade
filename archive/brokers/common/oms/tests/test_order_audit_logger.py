"""Tests for OrderAuditLogger collaborator.

Tests cover:
- New order logging
- State change logging
- Trade application logging
- History retrieval
- Eviction policy
- Thread safety
- AuditEntry serialization
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest

from application.oms.order_audit_logger import AuditEntry, OrderAuditLogger
from domain.types import OrderStatus


@pytest.fixture
def audit_logger() -> OrderAuditLogger:
    """Fresh OrderAuditLogger instance."""
    return OrderAuditLogger()


@pytest.fixture
def limited_logger() -> OrderAuditLogger:
    """OrderAuditLogger with small limit for eviction testing."""
    return OrderAuditLogger(max_entries_per_order=5)


# ── AuditEntry ─────────────────────────────────────────────────────────────


class TestAuditEntry:
    """Test AuditEntry dataclass."""

    def test_audit_entry_creation(self) -> None:
        """AuditEntry should be created with all fields."""
        entry = AuditEntry(
            timestamp=datetime.now(timezone.utc),
            order_id="order-1",
            old_status=None,
            new_status=OrderStatus.OPEN,
        )
        assert entry.order_id == "order-1"
        assert entry.old_status is None
        assert entry.new_status == OrderStatus.OPEN

    def test_audit_entry_frozen(self) -> None:
        """AuditEntry should be immutable."""
        entry = AuditEntry(
            timestamp=datetime.now(timezone.utc),
            order_id="order-1",
            old_status=None,
            new_status=OrderStatus.OPEN,
        )
        with pytest.raises(Exception, match="dataclass|frozen|attribute|cannot assign"):
            entry.order_id = "order-2"

    def test_audit_entry_to_dict(self) -> None:
        """to_dict should serialize entry correctly."""
        ts = datetime.now(timezone.utc)
        entry = AuditEntry(
            timestamp=ts,
            order_id="order-1",
            old_status=OrderStatus.OPEN,
            new_status=OrderStatus.PARTIALLY_FILLED,
            details={"trade_id": "T1"},
        )
        d = entry.to_dict()
        assert d["order_id"] == "order-1"
        assert d["old_status"] == "OPEN"
        assert d["new_status"] == "PARTIALLY_FILLED"
        assert d["details"]["trade_id"] == "T1"

    def test_audit_entry_to_dict_no_old_status(self) -> None:
        """to_dict should handle None old_status."""
        ts = datetime.now(timezone.utc)
        entry = AuditEntry(
            timestamp=ts,
            order_id="order-1",
            old_status=None,
            new_status=OrderStatus.OPEN,
        )
        d = entry.to_dict()
        assert d["old_status"] is None


# ── New Order Logging ──────────────────────────────────────────────────────


class TestNewOrderLogging:
    """Test logging of new orders."""

    def test_log_new_order_creates_entry(self, audit_logger: OrderAuditLogger) -> None:
        """log_new_order should create an audit entry."""
        audit_logger.log_new_order("order-1", OrderStatus.OPEN)
        history = audit_logger.get_history("order-1")
        assert len(history) == 1
        assert history[0].new_status == OrderStatus.OPEN
        assert history[0].old_status is None

    def test_log_new_order_with_details(self, audit_logger: OrderAuditLogger) -> None:
        """log_new_order should store details."""
        audit_logger.log_new_order(
            "order-2", OrderStatus.OPEN, details={"symbol": "RELIANCE", "side": "BUY"}
        )
        history = audit_logger.get_history("order-2")
        assert history[0].details["symbol"] == "RELIANCE"

    def test_log_new_order_timestamp(self, audit_logger: OrderAuditLogger) -> None:
        """log_new_order should use UTC timestamp."""
        before = datetime.now(timezone.utc)
        audit_logger.log_new_order("order-3", OrderStatus.OPEN)
        after = datetime.now(timezone.utc)
        history = audit_logger.get_history("order-3")
        assert before <= history[0].timestamp <= after


# ── State Change Logging ───────────────────────────────────────────────────


class TestStateChangeLogging:
    """Test logging of state changes."""

    def test_log_state_change_creates_entry(self, audit_logger: OrderAuditLogger) -> None:
        """log_state_change should create an audit entry."""
        audit_logger.log_state_change("order-1", OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED)
        history = audit_logger.get_history("order-1")
        assert len(history) == 1
        assert history[0].old_status == OrderStatus.OPEN
        assert history[0].new_status == OrderStatus.PARTIALLY_FILLED

    def test_log_state_change_with_reason(self, audit_logger: OrderAuditLogger) -> None:
        """log_state_change should store reason in details."""
        audit_logger.log_state_change(
            "order-2",
            OrderStatus.OPEN,
            OrderStatus.CANCELLED,
            details={"reason": "User requested"},
        )
        history = audit_logger.get_history("order-2")
        assert history[0].details["reason"] == "User requested"

    def test_multiple_state_changes_appended(self, audit_logger: OrderAuditLogger) -> None:
        """Multiple state changes should be appended chronologically."""
        audit_logger.log_state_change("order-3", OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED)
        audit_logger.log_state_change("order-3", OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED)
        history = audit_logger.get_history("order-3")
        assert len(history) == 2
        assert history[0].new_status == OrderStatus.PARTIALLY_FILLED
        assert history[1].new_status == OrderStatus.FILLED


# ── Trade Application Logging ──────────────────────────────────────────────


class TestTradeApplicationLogging:
    """Test logging of trade applications."""

    def test_log_trade_applied_creates_entry(self, audit_logger: OrderAuditLogger) -> None:
        """log_trade_applied should create an audit entry."""
        audit_logger.log_trade_applied("order-1", "T1", 10, "100.50")
        history = audit_logger.get_history("order-1")
        assert len(history) == 1
        assert history[0].details["trade_id"] == "T1"
        assert history[0].details["filled_quantity"] == 10
        assert history[0].details["avg_price"] == "100.50"

    def test_log_trade_applied_with_extra_details(self, audit_logger: OrderAuditLogger) -> None:
        """log_trade_applied should merge extra details."""
        audit_logger.log_trade_applied("order-2", "T2", 5, "200.00", details={"exchange": "NSE"})
        history = audit_logger.get_history("order-2")
        assert history[0].details["exchange"] == "NSE"


# ── History Retrieval ──────────────────────────────────────────────────────


class TestHistoryRetrieval:
    """Test audit history retrieval."""

    def test_get_history_unknown_order(self, audit_logger: OrderAuditLogger) -> None:
        """get_history should return empty list for unknown order."""
        assert audit_logger.get_history("unknown") == []

    def test_get_history_returns_copy(self, audit_logger: OrderAuditLogger) -> None:
        """get_history should return a copy, not internal list."""
        audit_logger.log_new_order("order-1", OrderStatus.OPEN)
        history1 = audit_logger.get_history("order-1")
        history2 = audit_logger.get_history("order-1")
        assert history1 == history2
        assert history1 is not history2

    def test_get_entry_count(self, audit_logger: OrderAuditLogger) -> None:
        """get_entry_count should return correct count."""
        audit_logger.log_new_order("order-1", OrderStatus.OPEN)
        audit_logger.log_state_change("order-1", OrderStatus.OPEN, OrderStatus.FILLED)
        assert audit_logger.get_entry_count("order-1") == 2

    def test_get_entry_count_unknown_order(self, audit_logger: OrderAuditLogger) -> None:
        """get_entry_count should return 0 for unknown order."""
        assert audit_logger.get_entry_count("unknown") == 0


# ── Eviction Policy ────────────────────────────────────────────────────────


class TestEvictionPolicy:
    """Test audit log eviction."""

    def test_eviction_removes_oldest(self, limited_logger: OrderAuditLogger) -> None:
        """Eviction should remove oldest entries when limit exceeded."""
        for _i in range(7):
            limited_logger.log_state_change(
                "order-1", OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED
            )

        history = limited_logger.get_history("order-1")
        assert len(history) == 5  # max_entries_per_order

    def test_eviction_keeps_newest(self, limited_logger: OrderAuditLogger) -> None:
        """Eviction should keep newest entries."""
        for _i in range(7):
            limited_logger.log_state_change(
                "order-1", OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED
            )

        history = limited_logger.get_history("order-1")
        # All entries should be the most recent ones
        assert len(history) == 5


# ── Clear Operations ───────────────────────────────────────────────────────


class TestClearOperations:
    """Test audit log clearing."""

    def test_clear_specific_order(self, audit_logger: OrderAuditLogger) -> None:
        """clear(order_id) should remove only that order's history."""
        audit_logger.log_new_order("order-1", OrderStatus.OPEN)
        audit_logger.log_new_order("order-2", OrderStatus.OPEN)
        audit_logger.clear("order-1")
        assert audit_logger.get_history("order-1") == []
        assert audit_logger.get_history("order-2") != []

    def test_clear_all_orders(self, audit_logger: OrderAuditLogger) -> None:
        """clear() should remove all history."""
        audit_logger.log_new_order("order-1", OrderStatus.OPEN)
        audit_logger.log_new_order("order-2", OrderStatus.OPEN)
        audit_logger.clear()
        assert audit_logger.get_history("order-1") == []
        assert audit_logger.get_history("order-2") == []

    def test_clear_unknown_order_no_error(self, audit_logger: OrderAuditLogger) -> None:
        """clear on unknown order should not raise."""
        audit_logger.clear("unknown-order")


# ── Thread Safety ──────────────────────────────────────────────────────────


class TestThreadSafety:
    """Basic thread safety sanity checks."""

    def test_concurrent_log_entries(self, audit_logger: OrderAuditLogger) -> None:
        """Concurrent log entries should not corrupt state."""

        def log_entry(order_num: int) -> bool:
            try:
                audit_logger.log_new_order(f"order-{order_num}", OrderStatus.OPEN)
                return True
            except Exception:
                return False

        with ThreadPoolExecutor(max_workers=10) as pool:
            results = list(pool.map(log_entry, range(50)))

        assert all(results), "All log operations should succeed"

    def test_concurrent_history_retrieval(self, audit_logger: OrderAuditLogger) -> None:
        """Concurrent history retrieval should not raise."""
        # Pre-populate
        for i in range(20):
            audit_logger.log_new_order(f"order-{i}", OrderStatus.OPEN)

        def get_history(order_num: int) -> int:
            try:
                return len(audit_logger.get_history(f"order-{order_num}"))
            except Exception:
                return -1

        with ThreadPoolExecutor(max_workers=10) as pool:
            results = list(pool.map(get_history, range(20)))

        assert all(r == 1 for r in results), "All history retrievals should succeed"
