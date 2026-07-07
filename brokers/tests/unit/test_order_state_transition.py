"""Tests for Order.propose_transition() — domain state machine wiring.

Verifies that the Order entity uses the canonical transition table
from order_lifecycle.py to validate and apply status changes.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from brokers.domain import OrderStateError
from brokers.domain.entities import Order
from brokers.domain.enums import OrderStatus, OrderType, ProductType, Side, Validity


def _order(**overrides: object) -> Order:
    """Helper: create a minimal Order with defaults."""
    defaults = dict(
        order_id="ORD-001",
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=10,
        status=OrderStatus.PENDING,
        price=Decimal("2500"),
        order_type=OrderType.LIMIT,
        product_type=ProductType.INTRADAY,
        validity=Validity.DAY,
    )
    defaults.update(overrides)
    return Order(**defaults)  # type: ignore[arg-type]


class TestProposeTransition:
    """Order.propose_transition() validates against order_lifecycle."""

    def test_pending_to_open(self) -> None:
        """PENDING → OPEN is legal."""
        order = _order(status=OrderStatus.PENDING)
        new = order.propose_transition(OrderStatus.OPEN)
        assert new.status is OrderStatus.OPEN
        assert new.order_id == order.order_id  # all other fields preserved

    def test_pending_to_rejected(self) -> None:
        """PENDING → REJECTED is legal."""
        order = _order(status=OrderStatus.PENDING)
        new = order.propose_transition(OrderStatus.REJECTED)
        assert new.status is OrderStatus.REJECTED

    def test_pending_to_cancelled(self) -> None:
        """PENDING → CANCELLED is legal."""
        order = _order(status=OrderStatus.PENDING)
        new = order.propose_transition(OrderStatus.CANCELLED)
        assert new.status is OrderStatus.CANCELLED

    def test_pending_to_expired(self) -> None:
        """PENDING → EXPIRED is legal."""
        order = _order(status=OrderStatus.PENDING)
        new = order.propose_transition(OrderStatus.EXPIRED)
        assert new.status is OrderStatus.EXPIRED

    def test_pending_to_filled_raises(self) -> None:
        """PENDING → FILLED is illegal (must go through OPEN first)."""
        order = _order(status=OrderStatus.PENDING)
        with pytest.raises(OrderStateError):
            order.propose_transition(OrderStatus.FILLED)

    def test_open_to_partially_filled(self) -> None:
        """OPEN → PARTIALLY_FILLED is legal."""
        order = _order(status=OrderStatus.OPEN)
        new = order.propose_transition(OrderStatus.PARTIALLY_FILLED)
        assert new.status is OrderStatus.PARTIALLY_FILLED

    def test_open_to_filled(self) -> None:
        """OPEN → FILLED is legal."""
        order = _order(status=OrderStatus.OPEN)
        new = order.propose_transition(OrderStatus.FILLED)
        assert new.status is OrderStatus.FILLED

    def test_open_to_cancelled(self) -> None:
        """OPEN → CANCELLED is legal."""
        order = _order(status=OrderStatus.OPEN)
        new = order.propose_transition(OrderStatus.CANCELLED)
        assert new.status is OrderStatus.CANCELLED

    def test_filled_is_terminal(self) -> None:
        """FILLED → anything is illegal."""
        order = _order(status=OrderStatus.FILLED)
        for status in {
            OrderStatus.OPEN,
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
        }:
            with pytest.raises(OrderStateError):
                order.propose_transition(status)

    def test_cancelled_is_terminal(self) -> None:
        """CANCELLED → anything is illegal."""
        order = _order(status=OrderStatus.CANCELLED)
        with pytest.raises(OrderStateError):
            order.propose_transition(OrderStatus.OPEN)

    def test_rejected_is_terminal(self) -> None:
        """REJECTED → anything is illegal."""
        order = _order(status=OrderStatus.REJECTED)
        with pytest.raises(OrderStateError):
            order.propose_transition(OrderStatus.OPEN)

    def test_returns_new_instance(self) -> None:
        """Original Order is NOT mutated (frozen dataclass guarantee)."""
        order = _order(status=OrderStatus.PENDING)
        _ = order.propose_transition(OrderStatus.OPEN)
        assert order.status is OrderStatus.PENDING  # original unchanged

    def test_all_other_fields_preserved(self) -> None:
        """transitioned Order retains all non-status fields."""
        order = _order(
            order_id="TEST-007",
            symbol="INFY",
            exchange="NSE",
            side=Side.SELL,
            quantity=25,
            price=Decimal("1800"),
            trigger_price=Decimal("0"),
            order_type=OrderType.MARKET,
            product_type=ProductType.DELIVERY,
            validity=Validity.DAY,
            status=OrderStatus.PENDING,
        )
        new = order.propose_transition(OrderStatus.OPEN)
        assert new.order_id == "TEST-007"
        assert new.symbol == "INFY"
        assert new.exchange == "NSE"
        assert new.side is Side.SELL
        assert new.quantity == 25
        assert new.price == Decimal("1800")
        assert new.order_type is OrderType.MARKET
        assert new.product_type is ProductType.DELIVERY

    def test_immutability_preserved(self) -> None:
        """transitioned Order is still frozen."""
        order = _order(status=OrderStatus.PENDING)
        new = order.propose_transition(OrderStatus.OPEN)
        with pytest.raises(Exception):
            new.quantity = 99  # type: ignore[misc]

    def test_identity(self) -> None:
        """Two Orders with same fields are equal (frozen dataclass)."""
        a = _order(status=OrderStatus.OPEN)
        b = _order(status=OrderStatus.OPEN)
        assert a == b
        assert hash(a) == hash(b)
