"""No-op event publisher for market layer defaults."""

from __future__ import annotations

from brokers.domain.events import DomainEvent


class NullEventPublisher:
    """Discards published events — used when no bus is injected."""

    def publish(self, event: DomainEvent) -> None:
        return None
