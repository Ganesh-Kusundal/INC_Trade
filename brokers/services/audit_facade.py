"""Public audit-trail facade for BrokerSession.

Wraps ``OrderRepository.history_for()`` to provide a stable, read-only
view of order state transitions recorded by the OMS.

The facade is intentionally thin: it adds a ``last_change()`` convenience
on top of the repository's history accessor and guarantees a read-only
public API that mirrors the value objects it returns.
"""

from __future__ import annotations

from typing import Any


class AuditFacade:
    """Read-only facade over the OMS audit trail.

    The facade holds no mutable state beyond its repository reference,
    so a single instance is safe to share across threads when paired
    with a thread-safe ``OrderRepository`` (the default).

    The repository is duck-typed: only ``history_for(order_id)`` is
    required. This keeps the facade decoupled from the concrete
    ``OrderRepository`` and lets it live in the ``services`` layer
    without violating the layer's import boundary.
    """

    def __init__(self, repository: Any) -> None:
        self._repository = repository

    def history_for(self, order_id: str) -> Any:
        """Return the full audit history for a given order.

        If the order has no recorded history, returns an empty
        ``OrderStateHistory`` (with the same order_id and an empty
        tuple) — never ``None``, so callers can iterate unconditionally.
        """
        return self._repository.history_for(order_id)

    def last_change(self, order_id: str) -> Any:
        """Return the most recent state change, or ``None`` if no history exists."""
        return self.history_for(order_id).last_change()

    def __repr__(self) -> str:
        return f"AuditFacade(repository={self._repository!r})"
