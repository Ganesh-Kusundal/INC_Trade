"""RoutingStrategy — function-based routing inside the provider.

Replaces the ``BrokerRouter`` class hierarchy.  ``RoutingStrategy`` is a
frozen dataclass with function fields: ``select_for_quote``,
``select_for_history``, ``select_for_execution``, ``select_for_streaming``.

The :class:`CompositeProvider` calls these functions to select which
sub-provider to delegate to.  No separate Router class needed.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


# Type alias for a routing function: (operation context) → provider index
# Returns the index into the provider list, or -1 for "none available"
RouteFn = Callable[..., int]


@dataclass(frozen=True, slots=True)
class RoutingStrategy:
    """Frozen dataclass with function fields for routing decisions.

    Each field is a function that receives operation context and returns
    the index of the provider to use.  This is a Strategy, not a class
    hierarchy — no Router class needed.

    Usage::

        strategy = RoutingStrategy(
            execution=lambda: 0,           # always primary
            market_data=lambda ctx: 0,     # always primary
            historical=lambda ctx: 1,      # always secondary
            streaming=lambda ctx: 0,       # always primary
        )
    """

    execution: RouteFn = field(default=lambda: 0)
    market_data: RouteFn = field(default=lambda *a, **kw: 0)
    historical: RouteFn = field(default=lambda *a, **kw: 0)
    streaming: RouteFn = field(default=lambda *a, **kw: 0)

    # ── Factory methods ──────────────────────────────────────────────

    @staticmethod
    def primary_only() -> RoutingStrategy:
        """All operations go to the primary provider (index 0)."""
        return RoutingStrategy()

    @staticmethod
    def failover() -> RoutingStrategy:
        """Read from the secondary, execute on the primary; failover on error.

        Market data, historical, and streaming operations prefer the
        secondary provider (index 1) so reads are served from a replica,
        while execution prefers the primary (index 0).  The
        ``CompositeProvider`` still fails over to the other provider when a
        call errors, so this is genuinely different from ``primary_only()``.
        """
        return RoutingStrategy(
            execution=lambda *a, **kw: 0,
            market_data=lambda *a, **kw: 1,
            historical=lambda *a, **kw: 1,
            streaming=lambda *a, **kw: 1,
        )

    @staticmethod
    def custom(
        *,
        execution: RouteFn | None = None,
        market_data: RouteFn | None = None,
        historical: RouteFn | None = None,
        streaming: RouteFn | None = None,
    ) -> RoutingStrategy:
        """Build a custom routing strategy with specific functions."""
        def default_fn(*a, **kw):
            return 0
        return RoutingStrategy(
            execution=execution or default_fn,
            market_data=market_data or default_fn,
            historical=historical or default_fn,
            streaming=streaming or default_fn,
        )


__all__ = ["RoutingStrategy"]
