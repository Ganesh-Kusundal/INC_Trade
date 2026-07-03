"""Domain events — immutable value objects for the event bus."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class DomainEvent:
    """Immutable domain event published on the in-process event bus."""

    event_type: str
    payload: dict[str, Any]
    symbol: str | None = None
    source: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def now(
        cls,
        event_type: str,
        payload: dict[str, Any],
        *,
        symbol: str | None = None,
        source: str | None = None,
    ) -> DomainEvent:
        return cls(
            event_type=event_type,
            payload=payload,
            symbol=symbol,
            source=source,
            timestamp=datetime.now(timezone.utc),
        )
