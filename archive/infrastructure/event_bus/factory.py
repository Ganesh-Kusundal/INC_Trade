"""EventBus factory helpers.

Provides :func:`create_domain_event` for dependency-injection wiring.
"""

from __future__ import annotations

import logging
from typing import Any

from infrastructure.event_bus.event_bus import DomainEvent

logger = logging.getLogger(__name__)


def create_domain_event(**kwargs: Any) -> DomainEvent:
    """Build a domain event with current timestamp (composition-root helper)."""
    return DomainEvent.now(**kwargs)


class AsyncEventBusFactory:
    """Factory for creating EventBus instances for async contexts.

    Despite the name, this creates the standard synchronous EventBus
    which is thread-safe and suitable for use in async applications.

    The 'async' label indicates the intended usage context (API/async
    consumers), not the bus implementation. The EventBus remains
    synchronous for minimum latency. Async consumers (WebSocket bridges)
    use bounded asyncio.Queue adapters (see MarketBridge).

    This factory is a composition-root helper that centralizes EventBus
    creation for the API bootstrap path. It returns a tuple matching
    the contract expected by runtime/trading_runtime_factory.py.
    """

    @classmethod
    def create_from_config(
        cls,
        *,
        force_async: bool = False,
        maxsize: int = 2000,
    ) -> tuple[Any, dict[str, Any]]:
        """Create an EventBus configured for API/async usage.

        Args:
            force_async: Reserved for future use (currently ignored).
                        The EventBus is intentionally synchronous.
            maxsize: Reserved for future use (currently ignored).
                    The EventBus has no queue size limit; backpressure
                    is handled at the MarketBridge layer.

        Returns:
            Tuple of (EventBus instance, config dict).
            The config dict contains metadata for diagnostics.
            The second element is typically discarded by callers.

        Example:
            >>> bus, config = AsyncEventBusFactory.create_from_config(
            ...     force_async=True, maxsize=2000
            ... )
            >>> isinstance(bus, EventBus)
            True
        """
        from infrastructure.event_bus.event_bus import EventBus

        event_bus = EventBus()

        config = {
            "force_async": force_async,
            "maxsize": maxsize,
            "created_by": "AsyncEventBusFactory",
            "bus_type": "synchronous",
            "note": "EventBus is intentionally sync; async bridge is MarketBridge",
        }

        logger.info(
            "AsyncEventBusFactory created EventBus (force_async=%s, maxsize=%d)",
            force_async,
            maxsize,
        )

        return event_bus, config


__all__ = [
    "AsyncEventBusFactory",
    "create_domain_event",
]
