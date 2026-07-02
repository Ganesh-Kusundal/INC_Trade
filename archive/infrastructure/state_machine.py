"""Generic state machine with illegal transition protection.

This module provides a reusable state machine that enforces explicit
state transitions and raises IllegalTransitionError when invalid
transitions are attempted.

The state machine is used by:
- Order lifecycle (OPEN → PARTIALLY_FILLED → FILLED)
- Position lifecycle (FLAT → OPEN → CLOSED)
- Scanner lifecycle (IDLE → RUNNING → COMPLETED)
- Strategy lifecycle (INACTIVE → ACTIVE → DISABLED)

Usage:
    transitions = {
        OrderStatus.PENDING_RISK: frozenset({OrderStatus.OPEN, OrderStatus.REJECTED}),
        OrderStatus.OPEN: frozenset({OrderStatus.PARTIALLY_FILLED, OrderStatus.CANCELLED}),
        OrderStatus.PARTIALLY_FILLED: frozenset({OrderStatus.FILLED, OrderStatus.CANCELLED}),
        OrderStatus.FILLED: frozenset(),  # Terminal
        OrderStatus.CANCELLED: frozenset(),  # Terminal
        OrderStatus.REJECTED: frozenset(),  # Terminal
    }
    sm = StateMachine(transitions, initial=OrderStatus.PENDING_RISK)
    sm.transition_to(OrderStatus.OPEN)  # OK
    sm.transition_to(OrderStatus.FILLED)  # Raises IllegalTransitionError
"""

from __future__ import annotations

from typing import Generic, TypeVar

from domain.exceptions import TradeXV2Error

T = TypeVar("T", bound=str)


class IllegalTransitionError(TradeXV2Error):
    """Raised when an invalid state transition is attempted.

    Attributes
    ----------
    from_state:
        The current state before the attempted transition.
    to_state:
        The requested target state.
    """

    def __init__(self, from_state: T, to_state: T) -> None:
        super().__init__(f"Illegal transition: {from_state} → {to_state}")
        self.from_state = from_state
        self.to_state = to_state


class StateMachine(Generic[T]):
    """Generic state machine with explicit transition validation.

    Parameters
    ----------
    transitions:
        Dictionary mapping each state to the set of allowed next states.
        Terminal states should map to an empty frozenset.
    initial:
        The initial state of the state machine.

    Thread Safety
    -------------
    The state machine itself is NOT thread-safe. Callers must provide
    external synchronization (e.g., RLock in OrderManager) if the
    state machine is shared across threads.

    Examples
    --------
    >>> from brokers.common.core.types import OrderStatus
    >>> transitions = {
    ...     OrderStatus.OPEN: frozenset({OrderStatus.PARTIALLY_FILLED, OrderStatus.CANCELLED}),
    ...     OrderStatus.PARTIALLY_FILLED: frozenset({OrderStatus.FILLED}),
    ...     OrderStatus.FILLED: frozenset(),
    ...     OrderStatus.CANCELLED: frozenset(),
    ... }
    >>> sm = StateMachine(transitions, initial=OrderStatus.OPEN)
    >>> sm.can_transition_to(OrderStatus.PARTIALLY_FILLED)
    True
    >>> sm.transition_to(OrderStatus.PARTIALLY_FILLED)
    >>> sm.state
    'PARTIALLY_FILLED'
    >>> sm.can_transition_to(OrderStatus.OPEN)  # Already passed this state
    False
    """

    def __init__(
        self,
        transitions: dict[T, frozenset[T]],
        initial: T,
    ) -> None:
        self._transitions = transitions
        self._state = initial

    @property
    def state(self) -> T:
        """Current state."""
        return self._state

    @property
    def is_terminal(self) -> bool:
        """True if the current state is terminal (no allowed transitions)."""
        allowed = self._transitions.get(self._state, frozenset())
        return len(allowed) == 0

    def can_transition_to(self, new_state: T) -> bool:
        """Check if a transition to ``new_state`` is allowed.

        Parameters
        ----------
        new_state:
            The requested target state.

        Returns
        -------
        bool:
            True if the transition is allowed, False otherwise.
        """
        allowed = self._transitions.get(self._state, frozenset())
        return new_state in allowed

    def transition_to(self, new_state: T) -> None:
        """Attempt to transition to ``new_state``.

        Parameters
        ----------
        new_state:
            The requested target state.

        Raises
        ------
        IllegalTransitionError:
            If the transition is not allowed from the current state.
        """
        if not self.can_transition_to(new_state):
            raise IllegalTransitionError(self._state, new_state)
        self._state = new_state

    def reset(self, new_state: T | None = None) -> None:
        """Reset the state machine to a new state.

        This bypasses transition validation and is intended for
        testing and recovery scenarios only.

        Parameters
        ----------
        new_state:
            The new state to reset to. If None, resets to the initial state.
        """
        self._state = new_state or self._transitions.__iter__().__next__()

    def __repr__(self) -> str:
        return f"StateMachine(state={self._state!r}, terminal={self.is_terminal})"


__all__ = [
    "IllegalTransitionError",
    "StateMachine",
]
