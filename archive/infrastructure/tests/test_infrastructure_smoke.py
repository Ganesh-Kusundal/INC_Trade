"""Infrastructure layer smoke tests."""

from __future__ import annotations

from domain.events.types import DomainEvent
from infrastructure.event_bus import EventBus
from infrastructure.event_log import EventLog
from infrastructure.lifecycle import HealthState, LifecycleManager, build_health


def test_event_log_append_and_replay(tmp_path):
    log = EventLog(events_dir=tmp_path / "events")
    bus = EventBus(event_log=log)
    bus.publish(DomainEvent.now("TICK", {"price": 100}, symbol="INFY", source="test"))
    events = list(log.replay())
    assert len(events) == 1
    assert events[0].event_type == "TICK"


def test_lifecycle_manager_start_stop():
    lifecycle = LifecycleManager()
    started = []

    class _Svc:
        name = "test.svc"

        def start(self) -> None:
            started.append(True)

        def stop(self, timeout_seconds: float = 30.0) -> None:
            started.clear()

        def health(self):
            return build_health(self.name, HealthState.HEALTHY)

    lifecycle.register(_Svc())
    lifecycle.start_all()
    assert started
    lifecycle.stop_all()
    assert not started
