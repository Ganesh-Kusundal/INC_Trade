"""Tests for event schema versioning and replay infrastructure."""

from __future__ import annotations

import time
from datetime import datetime, timezone

import pytest

from infrastructure.event_bus.event_bus import DomainEvent
from infrastructure.events.replay import EventReplayStore
from infrastructure.events.schema import EventSchema, SchemaRegistry
from infrastructure.events.versioned_event import VersionedEvent
from infrastructure.observability.event_metrics import EventMetrics

# ── Schema versioning tests ────────────────────────────────────────────


class TestEventSchema:
    def test_base_schema_defaults(self):
        schema = EventSchema()
        assert schema.version == 1
        assert schema.event_type == ""
        assert schema.schema_version == 1

    def test_migrate_from_noop(self):
        data = {"event_type": "TRADE", "payload": {"qty": 10}}
        result = EventSchema.migrate_from(data)
        assert result == data


class TestSchemaRegistry:
    def test_register_and_get(self):
        registry = SchemaRegistry()
        registry.register_schema("TRADE", 1, EventSchema)
        schema = registry.get_schema("TRADE", 1)
        assert schema is EventSchema

    def test_register_duplicate_raises(self):
        registry = SchemaRegistry()
        registry.register_schema("TRADE", 1, EventSchema)
        with pytest.raises(ValueError, match="already registered"):
            registry.register_schema("TRADE", 1, EventSchema)

    def test_get_missing_raises(self):
        registry = SchemaRegistry()
        with pytest.raises(KeyError, match="No schema registered"):
            registry.get_schema("TRADE", 99)

    def test_has_schema(self):
        registry = SchemaRegistry()
        registry.register_schema("TRADE", 1, EventSchema)
        assert registry.has_schema("TRADE", 1)
        assert not registry.has_schema("TRADE", 2)

    def test_latest_version(self):
        registry = SchemaRegistry()
        registry.register_schema("TRADE", 1, EventSchema)
        registry.register_schema("TRADE", 3, EventSchema)
        assert registry.latest_version("TRADE") == 3
        assert registry.latest_version("ORDER") == 0

    def test_migrate_event(self):
        class V1Schema(EventSchema):
            version = 1
            event_type = "TRADE"
            schema_version = 1

        class V2Schema(EventSchema):
            version = 2
            event_type = "TRADE"
            schema_version = 2

            @classmethod
            def migrate_from(cls, data):
                data = dict(data)
                data["payload"] = {
                    "quantity": data["payload"].get("qty", 0),
                    "price": data["payload"].get("price", 0.0),
                }
                return data

        registry = SchemaRegistry()
        registry.register_schema("TRADE", 1, V1Schema)
        registry.register_schema("TRADE", 2, V2Schema)

        old_event = {
            "event_type": "TRADE",
            "schema_version": 1,
            "payload": {"qty": 10, "price": 100.0},
        }
        migrated = registry.migrate_event(old_event, from_version=1, to_version=2)
        assert migrated["schema_version"] == 2
        assert migrated["payload"] == {"quantity": 10, "price": 100.0}

    def test_migrate_noop_when_same_version(self):
        registry = SchemaRegistry()
        data = {"event_type": "TRADE", "schema_version": 1}
        result = registry.migrate_event(data, from_version=1, to_version=1)
        assert result == data


# ── VersionedEvent tests ──────────────────────────────────────────────


def _make_event(**kwargs) -> DomainEvent:
    defaults = {
        "event_type": "TRADE",
        "timestamp": datetime.now(timezone.utc),
        "payload": {"qty": 10, "price": 100.0},
        "symbol": "RELIANCE",
    }
    defaults.update(kwargs)
    return DomainEvent(**defaults)


class TestVersionedEvent:
    def test_serialize(self):
        event = _make_event()
        ve = VersionedEvent(event=event, schema_version=2)
        data = ve.serialize()
        assert data["schema_version"] == 2
        assert data["event_type"] == "TRADE"
        assert data["symbol"] == "RELIANCE"
        assert data["payload"] == {"qty": 10, "price": 100.0}
        assert "timestamp" in data

    def test_deserialize(self):
        event = _make_event()
        ve = VersionedEvent(event=event, schema_version=1)
        data = ve.serialize()
        reconstructed = VersionedEvent.deserialize(data)
        assert reconstructed.schema_version == 1
        assert reconstructed.event.event_type == "TRADE"
        assert reconstructed.event.payload == {"qty": 10, "price": 100.0}

    def test_deserialize_with_migration(self):
        class V1Schema(EventSchema):
            version = 1
            event_type = "TRADE"
            schema_version = 1

        class V2Schema(EventSchema):
            version = 2
            event_type = "TRADE"
            schema_version = 2

            @classmethod
            def migrate_from(cls, data):
                data = dict(data)
                data["payload"] = {
                    "quantity": data["payload"].get("qty", 0),
                }
                return data

        registry = SchemaRegistry()
        registry.register_schema("TRADE", 1, V1Schema)
        registry.register_schema("TRADE", 2, V2Schema)

        old_data = {
            "schema_version": 1,
            "event_type": "TRADE",
            "timestamp": "2024-01-01T00:00:00+00:00",
            "payload": {"qty": 5},
            "symbol": "RELIANCE",
            "event_id": "abc123",
            "sequence_number": 0,
        }
        result = VersionedEvent.deserialize(
            old_data, registry=registry, target_version=2
        )
        assert result.schema_version == 2
        assert result.event.payload == {"quantity": 5}

    def test_from_domain_event(self):
        event = _make_event()
        ve = VersionedEvent.from_domain_event(event, schema_version=3)
        assert ve.schema_version == 3
        assert ve.event is event

    def test_json_roundtrip(self):
        event = _make_event()
        ve = VersionedEvent(event=event, schema_version=2)
        json_str = ve.to_json()
        reconstructed = VersionedEvent.from_json(json_str)
        assert reconstructed.schema_version == 2
        assert reconstructed.event.event_type == event.event_type
        assert reconstructed.event.payload == event.payload


# ── EventReplayStore tests ────────────────────────────────────────────


class TestEventReplayStore:
    def test_record_and_replay(self):
        store = EventReplayStore()
        e1 = _make_event(event_type="TRADE", payload={"qty": 1})
        e2 = _make_event(event_type="ORDER", payload={"side": "BUY"})

        store.record(e1)
        store.record(e2)

        events = list(store.replay())
        assert len(events) == 2
        assert events[0].payload == {"qty": 1}
        assert events[1].payload == {"side": "BUY"}

    def test_replay_time_range(self):
        store = EventReplayStore()
        e1 = _make_event(event_type="TRADE")
        store.record(e1)
        time.sleep(0.01)
        mid = time.time()
        time.sleep(0.01)
        e2 = _make_event(event_type="TRADE")
        store.record(e2)

        # Only events after mid
        events = list(store.replay(from_timestamp=mid))
        assert len(events) == 1
        assert events[0] is e2

    def test_replay_time_range_upper_bound(self):
        store = EventReplayStore()
        e1 = _make_event(event_type="TRADE")
        store.record(e1)
        time.sleep(0.01)
        cutoff = time.time()
        time.sleep(0.01)
        e2 = _make_event(event_type="TRADE")
        store.record(e2)

        events = list(store.replay(to_timestamp=cutoff))
        assert len(events) == 1
        assert events[0] is e1

    def test_replay_event_type_filter(self):
        store = EventReplayStore()
        e1 = _make_event(event_type="TRADE")
        e2 = _make_event(event_type="ORDER")
        e3 = _make_event(event_type="TRADE")

        store.record(e1)
        store.record(e2)
        store.record(e3)

        events = list(store.replay(event_type="TRADE"))
        assert len(events) == 2

    def test_replay_combined_filters(self):
        store = EventReplayStore()
        e1 = _make_event(event_type="TRADE")
        store.record(e1)
        time.sleep(0.01)
        mid = time.time()
        time.sleep(0.01)
        e2 = _make_event(event_type="ORDER")
        store.record(e2)

        events = list(store.replay(from_timestamp=mid, event_type="TRADE"))
        assert len(events) == 0

        events = list(store.replay(from_timestamp=mid, event_type="ORDER"))
        assert len(events) == 1

    def test_clear(self):
        store = EventReplayStore()
        store.record(_make_event())
        store.record(_make_event())
        assert store.count() == 2
        store.clear()
        assert store.count() == 0

    def test_count_with_filter(self):
        store = EventReplayStore()
        store.record(_make_event(event_type="TRADE"))
        store.record(_make_event(event_type="ORDER"))
        store.record(_make_event(event_type="TRADE"))
        assert store.count("TRADE") == 2
        assert store.count("ORDER") == 1
        assert store.count() == 3

    def test_replay_metrics_integration(self):
        metrics = EventMetrics()
        store = EventReplayStore(metrics=metrics)
        store.record(_make_event(event_type="TRADE"))
        store.record(_make_event(event_type="TRADE"))

        list(store.replay())
        assert metrics.get("event_replay", "replayed") == 2

    def test_file_backed_store(self, tmp_path):
        fp = tmp_path / "events.jsonl"
        store1 = EventReplayStore(file_path=fp)
        e1 = _make_event(event_type="TRADE", payload={"qty": 42})
        store1.record(e1)

        # Create a new store loading from the same file
        store2 = EventReplayStore(file_path=fp)
        events = list(store2.replay())
        assert len(events) == 1
        assert events[0].payload == {"qty": 42}
