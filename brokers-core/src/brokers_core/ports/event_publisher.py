"""Event publisher port — decouples adapters from infrastructure."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from brokers_core.domain.events import DomainEvent


@runtime_checkable
class EventPublisherPort(Protocol):
    def publish(self, event: DomainEvent) -> None: ...
