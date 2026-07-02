"""Tests for OrderStateValidator collaborator.

Tests cover:
- Valid transitions for all order statuses
- Invalid transitions raising IllegalTransitionError
- Audit mode (non-enforcement) behavior
- State machine lifecycle management
- Thread safety (basic sanity)
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from application.oms.order_state_validator import OrderStateValidator
from domain.types import OrderStatus
from infrastructure.state_machine import IllegalTransitionError


@pytest.fixture
def validator_enforce() -> OrderStateValidator:
    """OrderStateValidator in enforcement mode."""
    return OrderStateValidator(enforce=True)


@pytest.fixture
def validator_audit() -> OrderStateValidator:
    """OrderStateValidator in audit mode."""
    return OrderStateValidator(enforce=False)


# ── Valid Transitions ──────────────────────────────────────────────────────


class TestValidTransitions:
    """Test all valid order status transitions."""

    def test_open_to_partially_filled(self, validator_enforce: OrderStateValidator) -> None:
        """OPEN → PARTIALLY_FILLED is valid."""
        validator_enforce.validate_transition(
            "order-1", OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED
        )
        # Should not raise

    def test_open_to_cancelled(self, validator_enforce: OrderStateValidator) -> None:
        """OPEN → CANCELLED is valid."""
        validator_enforce.validate_transition("order-2", OrderStatus.OPEN, OrderStatus.CANCELLED)

    def test_open_to_rejected(self, validator_enforce: OrderStateValidator) -> None:
        """OPEN → REJECTED is valid."""
        validator_enforce.validate_transition("order-3", OrderStatus.OPEN, OrderStatus.REJECTED)

    def test_open_to_expired(self, validator_enforce: OrderStateValidator) -> None:
        """OPEN → EXPIRED is valid."""
        validator_enforce.validate_transition("order-4", OrderStatus.OPEN, OrderStatus.EXPIRED)

    def test_partially_filled_to_filled(self, validator_enforce: OrderStateValidator) -> None:
        """PARTIALLY_FILLED → FILLED is valid."""
        validator_enforce.validate_transition(
            "order-5", OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED
        )
        validator_enforce.validate_transition(
            "order-5", OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED
        )

    def test_partially_filled_to_cancelled(self, validator_enforce: OrderStateValidator) -> None:
        """PARTIALLY_FILLED → CANCELLED is valid."""
        validator_enforce.validate_transition(
            "order-6", OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED
        )
        validator_enforce.validate_transition(
            "order-6", OrderStatus.PARTIALLY_FILLED, OrderStatus.CANCELLED
        )

    def test_partially_filled_to_rejected(self, validator_enforce: OrderStateValidator) -> None:
        """PARTIALLY_FILLED → REJECTED is valid."""
        validator_enforce.validate_transition(
            "order-7", OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED
        )
        validator_enforce.validate_transition(
            "order-7", OrderStatus.PARTIALLY_FILLED, OrderStatus.REJECTED
        )

    def test_same_status_no_transition(self, validator_enforce: OrderStateValidator) -> None:
        """Same status should not trigger validation (no-op)."""
        # Should not raise even though OPEN → OPEN is not in transition table
        validator_enforce.validate_transition("order-8", OrderStatus.OPEN, OrderStatus.OPEN)

    def test_multiple_orders_independent(self, validator_enforce: OrderStateValidator) -> None:
        """Multiple orders should have independent state machines."""
        validator_enforce.validate_transition(
            "order-a", OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED
        )
        validator_enforce.validate_transition("order-b", OrderStatus.OPEN, OrderStatus.CANCELLED)
        # Both should succeed independently


# ── Invalid Transitions ────────────────────────────────────────────────────


class TestInvalidTransitions:
    """Test invalid transitions raising IllegalTransitionError."""

    def test_filled_to_open_raises(self, validator_enforce: OrderStateValidator) -> None:
        """FILLED → OPEN should raise IllegalTransitionError."""
        with pytest.raises(IllegalTransitionError) as exc_info:
            validator_enforce.validate_transition("order-10", OrderStatus.FILLED, OrderStatus.OPEN)
        assert exc_info.value.from_state == OrderStatus.FILLED
        assert exc_info.value.to_state == OrderStatus.OPEN

    def test_cancelled_to_open_raises(self, validator_enforce: OrderStateValidator) -> None:
        """CANCELLED → OPEN should raise IllegalTransitionError."""
        with pytest.raises(IllegalTransitionError) as exc_info:
            validator_enforce.validate_transition(
                "order-11", OrderStatus.CANCELLED, OrderStatus.OPEN
            )
        assert exc_info.value.from_state == OrderStatus.CANCELLED

    def test_rejected_to_partially_filled_raises(
        self, validator_enforce: OrderStateValidator
    ) -> None:
        """REJECTED → PARTIALLY_FILLED should raise IllegalTransitionError."""
        with pytest.raises(IllegalTransitionError):
            validator_enforce.validate_transition(
                "order-12", OrderStatus.REJECTED, OrderStatus.PARTIALLY_FILLED
            )

    def test_expired_to_filled_raises(self, validator_enforce: OrderStateValidator) -> None:
        """EXPIRED → FILLED should raise IllegalTransitionError."""
        with pytest.raises(IllegalTransitionError):
            validator_enforce.validate_transition(
                "order-13", OrderStatus.EXPIRED, OrderStatus.FILLED
            )

    def test_open_to_filled_is_allowed(self, validator_enforce: OrderStateValidator) -> None:
        """OPEN → FILLED is valid per ORDER_STATUS_TRANSITIONS."""
        validator_enforce.validate_transition("order-14", OrderStatus.OPEN, OrderStatus.FILLED)


# ── Audit Mode ─────────────────────────────────────────────────────────────


class TestAuditMode:
    """Test audit mode (non-enforcement) behavior."""

    def test_invalid_transition_logged_not_raised(
        self, validator_audit: OrderStateValidator
    ) -> None:
        """Invalid transition in audit mode should log but not raise."""
        # Should not raise in audit mode
        validator_audit.validate_transition("order-20", OrderStatus.FILLED, OrderStatus.OPEN)

    def test_audit_mode_creates_state_machine(self, validator_audit: OrderStateValidator) -> None:
        """Audit mode should still create state machines."""
        validator_audit.validate_transition(
            "order-21", OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED
        )
        sm = validator_audit.get_state_machine("order-21")
        assert sm is not None

    def test_enforce_property(
        self, validator_enforce: OrderStateValidator, validator_audit: OrderStateValidator
    ) -> None:
        """enforce property should reflect mode."""
        assert validator_enforce.enforce is True
        assert validator_audit.enforce is False


# ── State Machine Management ───────────────────────────────────────────────


class TestStateMachineManagement:
    """Test state machine lifecycle management."""

    def test_get_state_machine_new_order(self, validator_enforce: OrderStateValidator) -> None:
        """get_state_machine should return None for unknown order."""
        assert validator_enforce.get_state_machine("unknown-order") is None

    def test_get_state_machine_after_transition(
        self, validator_enforce: OrderStateValidator
    ) -> None:
        """get_state_machine should return state machine after transition."""
        validator_enforce.validate_transition(
            "order-30", OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED
        )
        sm = validator_enforce.get_state_machine("order-30")
        assert sm is not None
        assert sm.state == OrderStatus.PARTIALLY_FILLED

    def test_reset_removes_state_machine(self, validator_enforce: OrderStateValidator) -> None:
        """reset should remove state machine for order."""
        validator_enforce.validate_transition(
            "order-31", OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED
        )
        validator_enforce.reset("order-31")
        assert validator_enforce.get_state_machine("order-31") is None

    def test_reset_unknown_order_no_error(self, validator_enforce: OrderStateValidator) -> None:
        """reset on unknown order should not raise."""
        validator_enforce.reset("unknown-order")

    def test_clear_all_state_machines(self, validator_enforce: OrderStateValidator) -> None:
        """clear should remove all state machines."""
        validator_enforce.validate_transition(
            "order-1", OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED
        )
        validator_enforce.validate_transition("order-2", OrderStatus.OPEN, OrderStatus.CANCELLED)
        validator_enforce.clear()
        assert validator_enforce.get_state_machine("order-1") is None
        assert validator_enforce.get_state_machine("order-2") is None


# ── Custom Transitions ─────────────────────────────────────────────────────


class TestCustomTransitions:
    """Test custom transition tables."""

    def test_custom_transition_table(self) -> None:
        """Custom transitions should override defaults."""
        custom_transitions: dict[OrderStatus, frozenset[OrderStatus]] = {
            OrderStatus.OPEN: frozenset({OrderStatus.FILLED}),  # Only OPEN → FILLED
            OrderStatus.FILLED: frozenset(),
        }
        validator = OrderStateValidator(transitions=custom_transitions, enforce=True)

        # Should work with custom table
        validator.validate_transition("order-40", OrderStatus.OPEN, OrderStatus.FILLED)

        # Should fail with custom table (no PARTIALLY_FILLED in custom)
        with pytest.raises(IllegalTransitionError):
            validator.validate_transition(
                "order-41", OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED
            )


# ── Thread Safety ──────────────────────────────────────────────────────────


class TestThreadSafety:
    """Basic thread safety sanity checks."""

    def test_concurrent_transitions_different_orders(
        self, validator_enforce: OrderStateValidator
    ) -> None:
        """Concurrent transitions on different orders should not deadlock."""

        def transition(order_num: int) -> bool:
            try:
                order_id = f"order-{order_num}"
                validator_enforce.validate_transition(
                    order_id, OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED
                )
                validator_enforce.validate_transition(
                    order_id, OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED
                )
                return True
            except Exception:
                return False

        with ThreadPoolExecutor(max_workers=10) as pool:
            results = list(pool.map(transition, range(50)))

        assert all(results), "All transitions should succeed"

    def test_concurrent_resets(self, validator_enforce: OrderStateValidator) -> None:
        """Concurrent resets should not raise."""
        # First create some state machines
        for i in range(20):
            validator_enforce.validate_transition(
                f"order-{i}", OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED
            )

        def reset_order(order_num: int) -> bool:
            try:
                validator_enforce.reset(f"order-{order_num}")
                return True
            except Exception:
                return False

        with ThreadPoolExecutor(max_workers=10) as pool:
            results = list(pool.map(reset_order, range(20)))

        assert all(results), "All resets should succeed"
