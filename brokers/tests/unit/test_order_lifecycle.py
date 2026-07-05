"""Tests for order lifecycle state machine."""

from __future__ import annotations

import pytest

from inc_trade.domain.enums import OrderStatus
from inc_trade.domain.order_lifecycle import (
    ORDER_STATUS_TRANSITIONS,
    OrderStateError,
    is_valid_transition,
    validate_transition,
)


class TestOrderStatusTransitions:
    def test_pending_to_open(self):
        assert is_valid_transition(OrderStatus.PENDING, OrderStatus.OPEN)

    def test_pending_to_rejected(self):
        assert is_valid_transition(OrderStatus.PENDING, OrderStatus.REJECTED)

    def test_pending_to_cancelled(self):
        assert is_valid_transition(OrderStatus.PENDING, OrderStatus.CANCELLED)

    def test_pending_to_expired(self):
        assert is_valid_transition(OrderStatus.PENDING, OrderStatus.EXPIRED)

    def test_open_to_partially_filled(self):
        assert is_valid_transition(OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED)

    def test_open_to_filled(self):
        assert is_valid_transition(OrderStatus.OPEN, OrderStatus.FILLED)

    def test_open_to_cancelled(self):
        assert is_valid_transition(OrderStatus.OPEN, OrderStatus.CANCELLED)

    def test_open_to_partially_cancelled(self):
        assert is_valid_transition(OrderStatus.OPEN, OrderStatus.PARTIALLY_CANCELLED)

    def test_open_to_expired(self):
        assert is_valid_transition(OrderStatus.OPEN, OrderStatus.EXPIRED)

    def test_partially_filled_to_filled(self):
        assert is_valid_transition(OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED)

    def test_partially_filled_to_cancelled(self):
        assert is_valid_transition(OrderStatus.PARTIALLY_FILLED, OrderStatus.CANCELLED)

    def test_partially_cancelled_to_cancelled(self):
        assert is_valid_transition(
            OrderStatus.PARTIALLY_CANCELLED, OrderStatus.CANCELLED
        )

    def test_filled_is_terminal(self):
        assert ORDER_STATUS_TRANSITIONS[OrderStatus.FILLED] == frozenset()

    def test_cancelled_is_terminal(self):
        assert ORDER_STATUS_TRANSITIONS[OrderStatus.CANCELLED] == frozenset()

    def test_rejected_is_terminal(self):
        assert ORDER_STATUS_TRANSITIONS[OrderStatus.REJECTED] == frozenset()

    def test_expired_is_terminal(self):
        assert ORDER_STATUS_TRANSITIONS[OrderStatus.EXPIRED] == frozenset()


class TestInvalidTransitions:
    def test_filled_to_open_invalid(self):
        assert not is_valid_transition(OrderStatus.FILLED, OrderStatus.OPEN)

    def test_cancelled_to_pending_invalid(self):
        assert not is_valid_transition(OrderStatus.CANCELLED, OrderStatus.PENDING)

    def test_rejected_to_filled_invalid(self):
        assert not is_valid_transition(OrderStatus.REJECTED, OrderStatus.FILLED)

    def test_pending_to_filled_invalid(self):
        assert not is_valid_transition(OrderStatus.PENDING, OrderStatus.FILLED)


class TestValidateTransition:
    def test_valid_transition_no_error(self):
        validate_transition(OrderStatus.PENDING, OrderStatus.OPEN)

    def test_invalid_transition_raises(self):
        with pytest.raises(OrderStateError, match="Illegal transition"):
            validate_transition(OrderStatus.FILLED, OrderStatus.OPEN)

    def test_error_message_includes_statuses(self):
        with pytest.raises(OrderStateError, match="FILLED.*OPEN"):
            validate_transition(OrderStatus.FILLED, OrderStatus.OPEN)


class TestNewStatuses:
    def test_partially_cancelled_is_terminal(self):
        assert OrderStatus.PARTIALLY_CANCELLED.is_terminal

    def test_expired_is_terminal(self):
        assert OrderStatus.EXPIRED.is_terminal

    def test_partially_cancelled_not_active(self):
        assert not OrderStatus.PARTIALLY_CANCELLED.is_active

    def test_expired_not_active(self):
        assert not OrderStatus.EXPIRED.is_active
