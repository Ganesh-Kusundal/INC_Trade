"""Tests for the LifecycleManager and ManagedService protocol."""

from __future__ import annotations

import threading
import time
from typing import ClassVar

import pytest

from infrastructure.lifecycle import (
    HealthState,
    HealthStatus,
    LifecycleManager,
    ManagedService,
    build_health,
)


class _RecorderService(ManagedService):
    """A trivial service that records its lifecycle events."""

    instances: ClassVar[list[_RecorderService]] = []

    def __init__(self, name: str = "test.recorder") -> None:
        self.name = name
        self.start_count = 0
        self.stop_count = 0
        self.start_sleep: float = 0.0
        self.stop_sleep: float = 0.0
        self._healthy = True
        self._run_lock = threading.Lock()
        type(self).instances.append(self)

    def start(self) -> None:
        with self._run_lock:
            self.start_count += 1
            if self.start_sleep:
                time.sleep(self.start_sleep)

    def stop(self, timeout_seconds: float = 5.0) -> None:
        with self._run_lock:
            self.stop_count += 1
            if self.stop_sleep:
                time.sleep(self.stop_sleep)

    def health(self) -> HealthStatus:
        if self._healthy:
            return build_health(self.name, HealthState.HEALTHY, detail="ok")
        return build_health(self.name, HealthState.UNHEALTHY, detail="bad")


class _ExplodingService(ManagedService):
    def __init__(self, name: str) -> None:
        self.name = name

    def start(self) -> None:
        raise RuntimeError("boom")

    def stop(self, timeout_seconds: float = 5.0) -> None:
        pass

    def health(self) -> HealthStatus:
        return build_health(self.name, HealthState.HEALTHY)


@pytest.fixture(autouse=True)
def _reset():
    _RecorderService.instances = []
    yield
    _RecorderService.instances = []


# ── Registration ──────────────────────────────────────────────────────────


def test_register_and_get() -> None:
    mgr = LifecycleManager()
    svc = _RecorderService("svc.a")
    mgr.register(svc)
    assert mgr.get("svc.a") is svc
    assert mgr.service_names() == ["svc.a"]


def test_register_is_idempotent_on_name() -> None:
    mgr = LifecycleManager()
    a = _RecorderService("svc.a")
    b = _RecorderService("svc.a")
    mgr.register(a)
    mgr.register(b)
    assert mgr.get("svc.a") is b  # re-register replaces


def test_unregister_removes_service() -> None:
    mgr = LifecycleManager()
    svc = _RecorderService("svc.a")
    mgr.register(svc)
    mgr.unregister("svc.a")
    assert mgr.get("svc.a") is None
    assert mgr.service_names() == []


# ── Start / stop semantics ────────────────────────────────────────────────


def test_start_all_calls_start_in_registration_order() -> None:
    mgr = LifecycleManager()
    a = _RecorderService("svc.a")
    b = _RecorderService("svc.b")
    c = _RecorderService("svc.c")
    mgr.register(a)
    mgr.register(b)
    mgr.register(c)
    mgr.start_all()
    assert a.start_count == 1
    assert b.start_count == 1
    assert c.start_count == 1


def test_stop_all_calls_stop_in_reverse_registration_order() -> None:
    mgr = LifecycleManager()
    a = _RecorderService("svc.a")
    b = _RecorderService("svc.b")
    c = _RecorderService("svc.c")
    mgr.register(a)
    mgr.register(b)
    mgr.register(c)
    mgr.start_all()
    mgr.stop_all()
    # The last-registered should be the first stopped.
    assert c.stop_count == 1
    assert b.stop_count == 1
    assert a.stop_count == 1


def test_register_after_start_all_auto_starts_late_service() -> None:
    mgr = LifecycleManager()
    early = _RecorderService("svc.early")
    mgr.register(early)
    mgr.start_all()
    assert early.start_count == 1

    late = _RecorderService("svc.late")
    mgr.register(late)
    assert late.start_count == 1


def test_start_is_idempotent() -> None:
    mgr = LifecycleManager()
    svc = _RecorderService()
    mgr.register(svc)
    mgr.start_all()
    mgr.start_all()
    mgr.start_all()
    assert svc.start_count == 1


def test_stop_is_idempotent() -> None:
    mgr = LifecycleManager()
    svc = _RecorderService()
    mgr.register(svc)
    mgr.start_all()
    mgr.stop_all()
    mgr.stop_all()
    mgr.stop_all()
    assert svc.stop_count == 1


def test_exploding_start_does_not_abort_start_all() -> None:
    mgr = LifecycleManager()
    a = _RecorderService("svc.a")
    bad = _ExplodingService("svc.bad")
    c = _RecorderService("svc.c")
    mgr.register(a)
    mgr.register(bad)
    mgr.register(c)
    mgr.start_all()  # must not raise
    assert a.start_count == 1
    assert c.start_count == 1
    # Health snapshot records the failure.
    snap = mgr.health_snapshot()
    assert snap["svc.bad"]["state"] == HealthState.FAILED.value


# ── Health ────────────────────────────────────────────────────────────────


def test_health_snapshot_calls_each_service() -> None:
    mgr = LifecycleManager()
    a = _RecorderService("svc.a")
    b = _RecorderService("svc.b")
    mgr.register(a)
    mgr.register(b)
    mgr.start_all()  # health is only called for started services
    snap = mgr.health_snapshot()
    assert set(snap) == {"svc.a", "svc.b"}
    assert snap["svc.a"]["state"] == HealthState.HEALTHY.value
    assert snap["svc.b"]["state"] == HealthState.HEALTHY.value


def test_health_snapshot_swallows_exceptions_in_health() -> None:
    class _BrokenHealth(ManagedService):
        name = "svc.broken"

        def start(self) -> None:
            pass

        def stop(self, timeout_seconds: float = 5.0) -> None:
            pass

        def health(self) -> HealthStatus:
            raise RuntimeError("health broke")

    mgr = LifecycleManager()
    svc = _BrokenHealth()
    mgr.register(svc)
    mgr.start_all()
    snap = mgr.health_snapshot()
    assert snap["svc.broken"]["state"] == HealthState.FAILED.value
    assert "health broke" in snap["svc.broken"]["detail"]


def test_health_reflects_service_state() -> None:
    mgr = LifecycleManager()
    svc = _RecorderService("svc.a")
    mgr.register(svc)
    # Before start: STOPPED
    snap = mgr.health_snapshot()
    assert snap["svc.a"]["state"] == HealthState.STOPPED.value
    mgr.start_all()
    snap = mgr.health_snapshot()
    assert snap["svc.a"]["state"] == HealthState.HEALTHY.value
    mgr.stop_all()
    snap = mgr.health_snapshot()
    assert snap["svc.a"]["state"] == HealthState.STOPPED.value


# ── Stop timeout ─────────────────────────────────────────────────────────


def test_stop_timeout_does_not_hang() -> None:
    mgr = LifecycleManager(default_stop_timeout=0.1)
    svc = _RecorderService("svc.slow")
    svc.stop_sleep = 5.0  # try to hang stop
    mgr.register(svc)
    mgr.start_all()
    started = time.monotonic()
    mgr.stop_all()
    elapsed = time.monotonic() - started
    # Must return quickly even though stop_sleep is 5s.
    assert elapsed < 1.0


# ── Protocol conformance ──────────────────────────────────────────────────


def test_recorder_is_a_managed_service() -> None:
    svc = _RecorderService()
    assert isinstance(svc, ManagedService)


# ── build_health helper ──────────────────────────────────────────────────


def test_build_health_sets_last_check_to_now() -> None:
    before = time.time()
    status = build_health("svc.x", HealthState.HEALTHY, detail="d", metrics={"k": 1})
    after = time.time()
    assert before <= status.last_check.timestamp() <= after
    assert status.metrics == {"k": 1}
