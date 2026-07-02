"""Event schema versioning infrastructure.

Provides versioned schema registration, retrieval, and migration
for domain events. Works alongside the existing EventBus/DomainEvent
without modifying them.
"""

from __future__ import annotations

from typing import Any


class EventSchema:
    """Base class for versioned event schemas.

    Subclass this to define a schema for a specific event type at a
    specific version. Each schema declares its version, the event type
    it describes, and how to migrate to itself from a prior version.

    Attributes:
        version: The schema version number (starting at 1).
        event_type: The string event type this schema describes.
        schema_version: Alias for version (used in serialized output).
    """

    version: int = 1
    event_type: str = ""
    schema_version: int = 1

    @classmethod
    def migrate_from(cls, event_data: dict[str, Any]) -> dict[str, Any]:
        """Migrate event_data from the immediately prior version.

        Override this in subclasses that support migration. The default
        implementation is a no-op (assumes no structural changes).
        """
        return event_data


class SchemaRegistry:
    """Registry mapping (event_type, version) to schema classes.

    Usage:
        registry = SchemaRegistry()
        registry.register_schema("TRADE", 1, TradeV1Schema)
        registry.register_schema("TRADE", 2, TradeV2Schema)

        schema = registry.get_schema("TRADE", 2)
        migrated = registry.migrate_event(data, from_version=1, to_version=2)
    """

    def __init__(self) -> None:
        self._schemas: dict[tuple[str, int], type[EventSchema]] = {}

    def register_schema(
        self, event_type: str, version: int, schema_class: type[EventSchema]
    ) -> None:
        """Register a schema class for a given event_type and version."""
        key = (event_type, version)
        if key in self._schemas:
            raise ValueError(
                f"Schema already registered for ({event_type!r}, v{version})"
            )
        self._schemas[key] = schema_class

    def get_schema(self, event_type: str, version: int) -> type[EventSchema]:
        """Return the schema class for (event_type, version).

        Raises KeyError if no schema is registered for the given key.
        """
        key = (event_type, version)
        if key not in self._schemas:
            raise KeyError(f"No schema registered for ({event_type!r}, v{version})")
        return self._schemas[key]

    def has_schema(self, event_type: str, version: int) -> bool:
        """Return True if a schema is registered for (event_type, version)."""
        return (event_type, version) in self._schemas

    def latest_version(self, event_type: str) -> int:
        """Return the highest registered version for event_type, or 0."""
        versions = [v for (et, v) in self._schemas if et == event_type]
        return max(versions) if versions else 0

    def migrate_event(
        self,
        event_data: dict[str, Any],
        from_version: int,
        to_version: int,
    ) -> dict[str, Any]:
        """Migrate event_data from from_version to to_version.

        Applies migration step-by-step through each intermediate version.
        Each schema's migrate_from() is called to convert from the
        immediately prior version.
        """
        event_type = event_data.get("event_type", "")
        current_version = from_version

        while current_version < to_version:
            next_version = current_version + 1
            schema = self.get_schema(event_type, next_version)
            event_data = schema.migrate_from(event_data)
            event_data["schema_version"] = next_version
            current_version = next_version

        return event_data
