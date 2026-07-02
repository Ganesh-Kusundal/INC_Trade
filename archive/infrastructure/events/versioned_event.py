"""Versioned event wrapper for schema-aware serialization.

Wraps DomainEvent with schema_version metadata, enabling
serialize/deserialize with automatic migration support.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from infrastructure.event_bus.event_bus import DomainEvent
from infrastructure.events.schema import SchemaRegistry


@dataclass
class VersionedEvent:
    """A DomainEvent wrapped with schema version metadata.

    Attributes:
        event: The underlying DomainEvent.
        schema_version: The schema version of this event.
    """

    event: DomainEvent
    schema_version: int = 1

    def serialize(self) -> dict[str, Any]:
        """Return a JSON-serializable dict with version metadata."""
        return {
            "schema_version": self.schema_version,
            "event_type": self.event.event_type,
            "timestamp": self.event.timestamp.isoformat(),
            "payload": self.event.payload,
            "symbol": self.event.symbol,
            "source": self.event.source,
            "event_id": self.event.event_id,
            "correlation_id": self.event.correlation_id,
            "sequence_number": self.event.sequence_number,
        }

    @classmethod
    def deserialize(
        cls,
        data: dict[str, Any],
        registry: SchemaRegistry | None = None,
        target_version: int | None = None,
    ) -> VersionedEvent:
        """Reconstruct a VersionedEvent from a dict.

        If registry and target_version are provided and the event's
        schema_version < target_version, the event is automatically
        migrated to the target version before reconstruction.
        """
        schema_version = data.get("schema_version", 1)

        # Auto-migrate if needed
        if registry is not None and target_version is not None and schema_version < target_version:
                data = registry.migrate_event(
                    data,
                    from_version=schema_version,
                    to_version=target_version,
                )
                schema_version = target_version

        # Parse timestamp
        ts_raw = data["timestamp"]
        if isinstance(ts_raw, str):
            timestamp = datetime.fromisoformat(ts_raw)
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
        elif isinstance(ts_raw, datetime):
            timestamp = ts_raw
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
        else:
            raise ValueError(f"Cannot parse timestamp: {ts_raw}")

        event = DomainEvent(
            event_type=data["event_type"],
            timestamp=timestamp,
            payload=data.get("payload", {}),
            symbol=data.get("symbol"),
            source=data.get("source"),
            event_id=data.get("event_id", uuid.uuid4().hex[:16]),
            correlation_id=data.get("correlation_id"),
            sequence_number=data.get("sequence_number", 0),
        )

        return cls(event=event, schema_version=schema_version)

    @classmethod
    def from_domain_event(
        cls,
        event: DomainEvent,
        schema_version: int = 1,
    ) -> VersionedEvent:
        """Create a VersionedEvent from an existing DomainEvent."""
        return cls(event=event, schema_version=schema_version)

    def to_json(self) -> str:
        """Serialize to a JSON string."""
        return json.dumps(self.serialize())

    @classmethod
    def from_json(
        cls,
        json_str: str,
        registry: SchemaRegistry | None = None,
        target_version: int | None = None,
    ) -> VersionedEvent:
        """Deserialize from a JSON string."""
        data = json.loads(json_str)
        return cls.deserialize(data, registry=registry, target_version=target_version)
