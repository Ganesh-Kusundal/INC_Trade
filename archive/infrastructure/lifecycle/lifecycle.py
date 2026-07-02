"""Background-service lifecycle management.

Every daemon thread, scheduler, and long-running async worker in the
system MUST be owned by a :class:`LifecycleManager` so the SRE layer
can:

* **Start** services in the correct order.
* **Stop** them deterministically on shutdown.
* **Health-check** them at runtime.
* **Replace** them without process restart (e.g. on token expiry).

This module replaces the previous ad-hoc pattern of starting daemon
threads inside constructors and never stopping them.

Rule of thumb: **no thread without a lifecycle.**
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from domain.constants import DEFAULT_STOP_TIMEOUT_SECONDS
from domain.lifecycle_health import HealthState, HealthStatus

logger = logging.getLogger(__name__)


@runtime_checkable
class ManagedService(Protocol):
    """A long-running service that participates in the lifecycle.

    Implementations should:

    * Be idempotent on :meth:`start` and :meth:`stop`.
    * Make :meth:`start` return promptly; long-running work belongs in
      a background thread owned by the service.
    * Make :meth:`stop` drain cleanly and within a bounded timeout
      (caller enforces the timeout).
    * Make :meth:`health` cheap — it is polled continuously.
    """

    name: str

    def start(self) -> None:
        """Start the service. Idempotent. Returns when the service is up."""
        ...

    def stop(self, timeout_seconds: float = DEFAULT_STOP_TIMEOUT_SECONDS) -> None:
        """Stop the service. Idempotent. Returns when the service is down."""
        ...

    def health(self) -> HealthStatus:
        """Return a point-in-time health snapshot."""
        ...


# ── Manager ────────────────────────────────────────────────────────────────


class LifecycleManager:
    """Owns a set of :class:`ManagedService` instances.

    Use::

        manager = LifecycleManager()
        manager.register(TokenRefreshScheduler(...))
        manager.register(ReconciliationService(...))
        manager.start_all()
        # ... runtime ...
        manager.health_snapshot()   # for the SRE
        manager.stop_all()         # on shutdown

    Parameters
    ----------
    default_stop_timeout:
        Maximum number of seconds to wait for each service to stop
        before considering it stuck and moving on.
    health_check_interval:
        How often :meth:`health_snapshot` should be called to publish
        metrics (callers wire this up — the manager does not run a
        background thread itself).
    """

    def __init__(
        self,
        default_stop_timeout: float = DEFAULT_STOP_TIMEOUT_SECONDS,
    ) -> None:
        self._lock = threading.RLock()
        self._services: dict[str, ManagedService] = {}
        self._started: set[str] = set()
        self._start_failed: set[str] = set()
        self._start_all_invoked = False
        self._default_stop_timeout = default_stop_timeout
        self._start_order: list[str] = []
        self._stop_order: list[str] = []
        self._last_health: dict[str, HealthStatus] = {}

    # ── Registration ──────────────────────────────────────────────────────

    def register(self, service: ManagedService) -> None:
        """Register a service. Idempotent on name."""
        with self._lock:
            name = service.name
            if name in self._services:
                logger.debug("LifecycleManager: re-registering %s", name)
            self._services[name] = service
            if name not in self._start_order:
                self._start_order.append(name)
            if name in self._stop_order:
                self._stop_order.remove(name)
            self._stop_order.append(name)
            self._last_health[name] = HealthStatus(
                state=HealthState.STOPPED,
                service=name,
                last_check=datetime.now(timezone.utc),
                detail="registered",
            )
            start_all_invoked = self._start_all_invoked
        if start_all_invoked:
            self._start_one(name)

    def unregister(self, name: str) -> None:
        """Remove a service from the manager. Does not stop it."""
        with self._lock:
            self._services.pop(name, None)
            self._started.discard(name)
            self._start_failed.discard(name)
            self._start_order = [n for n in self._start_order if n != name]
            self._stop_order = [n for n in self._stop_order if n != name]
            self._last_health.pop(name, None)

    def get(self, name: str) -> ManagedService | None:
        with self._lock:
            return self._services.get(name)

    def service_names(self) -> list[str]:
        with self._lock:
            return list(self._services.keys())

    # ── Start / Stop ─────────────────────────────────────────────────────

    def start_all(self) -> None:
        """Start every registered service in registration order.

        A failure in one service does not prevent subsequent services
        from starting; the failure is recorded in :meth:`health_snapshot`.
        """
        with self._lock:
            self._start_all_invoked = True
            names = list(self._start_order)
        for name in names:
            self._start_one(name)

    def stop_all(self) -> None:
        """Stop every registered service in reverse-registration order.

        A service that does not stop within ``default_stop_timeout`` is
        abandoned and recorded as FAILED in the next health snapshot.
        """
        with self._lock:
            names = list(reversed(self._stop_order))
        for name in names:
            self._stop_one(name)

    def start(self, name: str) -> None:
        """Start a single service by name."""
        self._start_one(name)

    def stop(self, name: str, timeout_seconds: float | None = None) -> None:
        """Stop a single service by name."""
        self._stop_one(name, timeout_seconds=timeout_seconds)

    # ── Health ───────────────────────────────────────────────────────────

    def health_snapshot(self) -> dict[str, dict[str, Any]]:
        """Call ``health()`` on every started service and return a serializable view.

        Services that have not been started are reported as
        ``STOPPED`` without invoking their ``health()`` method.
        Services whose ``start()`` raised are reported as ``FAILED``.

        This is the snapshot the SRE polls. It is side-effect free
        (services must not mutate state in ``health()``).
        """
        snapshot: dict[str, dict[str, Any]] = {}
        with self._lock:
            names = list(self._services.keys())
            started = set(self._started)
            start_failed = set(self._start_failed)
            cached = dict(self._last_health)
        for name in names:
            if name in start_failed:
                snapshot[name] = cached.get(
                    name,
                    HealthStatus(
                        state=HealthState.FAILED,
                        service=name,
                        last_check=datetime.now(timezone.utc),
                        detail="start failed",
                    ),
                ).to_dict()
                continue
            if name not in started:
                status = HealthStatus(
                    state=HealthState.STOPPED,
                    service=name,
                    last_check=datetime.now(timezone.utc),
                    detail="not started",
                )
                with self._lock:
                    self._last_health[name] = status
                snapshot[name] = status.to_dict()
                continue
            try:
                status = self._services[name].health()
            except Exception as exc:
                status = HealthStatus(
                    state=HealthState.FAILED,
                    service=name,
                    last_check=datetime.now(timezone.utc),
                    detail=f"health() raised: {type(exc).__name__}: {exc}",
                )
            with self._lock:
                self._last_health[name] = status
            snapshot[name] = status.to_dict()
        return snapshot

    def last_health(self, name: str) -> HealthStatus | None:
        with self._lock:
            return self._last_health.get(name)

    # ── Internals ────────────────────────────────────────────────────────

    def _start_one(self, name: str) -> None:
        with self._lock:
            service = self._services.get(name)
            if name in self._started or name in self._start_failed:
                logger.debug(
                    "LifecycleManager.start: %s already in terminal state",
                    name,
                )
                return
        if service is None:
            logger.warning("LifecycleManager.start: %s not registered", name)
            return
        try:
            service.start()
            with self._lock:
                self._started.add(name)
                self._start_failed.discard(name)
            logger.info("LifecycleManager: %s started", name)
        except Exception as exc:
            logger.exception(
                "LifecycleManager: %s failed to start: %s: %s",
                name,
                type(exc).__name__,
                exc,
            )
            with self._lock:
                self._start_failed.add(name)
                self._last_health[name] = HealthStatus(
                    state=HealthState.FAILED,
                    service=name,
                    last_check=datetime.now(timezone.utc),
                    detail=f"start raised: {type(exc).__name__}: {exc}",
                )

    def _stop_one(self, name: str, timeout_seconds: float | None = None) -> None:
        with self._lock:
            service = self._services.get(name)
            if name not in self._started:
                logger.debug("LifecycleManager.stop: %s not started", name)
                return
        if service is None:
            return
        timeout = timeout_seconds if timeout_seconds is not None else self._default_stop_timeout
        # Enforce the timeout: run stop() in a daemon thread and join
        # with a hard deadline. If the service refuses to stop, we
        # mark it FAILED and move on — we never hang the process.
        container: dict[str, BaseException | None] = {"err": None}
        stop_thread = threading.Thread(
            target=self._run_stop,
            args=(service, container),
            daemon=True,
            name=f"lifecycle.stop.{name}",
        )
        stop_thread.start()
        stop_thread.join(timeout=timeout)
        if stop_thread.is_alive():
            logger.error(
                "LifecycleManager: %s did not stop within %.1fs; abandoning thread",
                name,
                timeout,
            )
            with self._lock:
                self._last_health[name] = HealthStatus(
                    state=HealthState.FAILED,
                    service=name,
                    last_check=datetime.now(timezone.utc),
                    detail=f"stop did not return within {timeout:.1f}s",
                )
            return
        if container["err"] is not None:
            logger.error(
                "LifecycleManager: %s failed to stop cleanly: %s: %s",
                name,
                type(container["err"]).__name__,
                container["err"],
            )
            with self._lock:
                self._last_health[name] = HealthStatus(
                    state=HealthState.FAILED,
                    service=name,
                    last_check=datetime.now(timezone.utc),
                    detail=f"stop raised: {container['err']}",
                )
            return
        with self._lock:
            self._started.discard(name)
        logger.info("LifecycleManager: %s stopped", name)

    @staticmethod
    def _run_stop(service: ManagedService, container: dict[str, BaseException | None]) -> None:
        try:
            service.stop()
        except BaseException as exc:
            container["err"] = exc


# ── Helpers ────────────────────────────────────────────────────────────────


def build_health(
    name: str,
    state: HealthState,
    detail: str = "",
    metrics: dict[str, Any] | None = None,
) -> HealthStatus:
    """Convenience constructor for subclasses implementing ``health()``."""
    return HealthStatus(
        state=state,
        service=name,
        last_check=datetime.now(timezone.utc),
        detail=detail,
        metrics=dict(metrics or {}),
    )


def now_monotonic() -> float:
    """Centralised monotonic clock for stop-time measurements."""
    return time.monotonic()
