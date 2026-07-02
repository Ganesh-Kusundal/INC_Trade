"""Unified resource lifecycle manager.

Tracks named resources and ensures deterministic cleanup in reverse order.
Supports both sync and async cleanup functions in the same instance.

Thread-safe via threading.Lock (sync methods) and lazy asyncio.Lock (async methods).

Usage:
    from infrastructure.resource_manager import ResourceManager

    rm = ResourceManager()
    rm.register("db_pool", pool, pool.close_all)
    rm.register("http_client", client, client.close)

    with rm.acquire("db_pool") as pool:
        conn = pool.acquire()

    # Or async:
    async with arm.async_acquire("db_pool") as pool:
        conn = await pool.acquire()

    # On shutdown (async):
    await rm.shutdown_all()
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from typing import Any

from infrastructure.health import HealthRegistry, HealthResult, HealthStatus

logger = logging.getLogger(__name__)


@dataclass
class _ResourceEntry:
    """Internal record for a registered resource."""
    resource: Any
    cleanup_fn: Callable[[], Any] | Callable[[], Awaitable[Any]] | None
    acquired: bool = False


class ResourceManager:
    """Manages named resources with deterministic cleanup.

    Resources are cleaned up in reverse registration order on shutdown.
    Supports both sync and async cleanup functions — the cleanup type is
    detected at call time via ``asyncio.iscoroutine()``.

    Thread-safe: sync methods use ``threading.Lock``; async methods lazily
    create an ``asyncio.Lock``.

    Parameters
    ----------
    health_registry:
        Optional HealthRegistry to integrate with. If provided,
        a health check is registered that reports resource status.
    """

    def __init__(self, health_registry: HealthRegistry | None = None) -> None:
        self._lock = threading.Lock()
        self._async_lock: asyncio.Lock | None = None
        self._resources: dict[str, _ResourceEntry] = {}
        self._shutdown_called = False
        self._health_registry = health_registry

        if health_registry is not None:
            health_registry.register("resources", self._health_check)

    def _get_async_lock(self) -> asyncio.Lock:
        """Lazily create asyncio.Lock to avoid issues when instantiated outside an event loop."""
        if self._async_lock is None:
            self._async_lock = asyncio.Lock()
        return self._async_lock

    def register(
        self,
        name: str,
        resource: Any,
        cleanup_fn: Callable[[], Any] | Callable[[], Awaitable[Any]] | None = None,
    ) -> None:
        """Register a resource with an optional cleanup function.

        Parameters
        ----------
        name:
            Unique name for the resource.
        resource:
            The resource object to track.
        cleanup_fn:
            Callable (sync or async) to clean up the resource. If None,
            no cleanup is performed.

        Raises
        ------
        ValueError
            If a resource with this name is already registered.
        """
        if cleanup_fn is None:
            def cleanup_fn():
                return None

        with self._lock:
            if name in self._resources:
                raise ValueError(f"Resource '{name}' is already registered")
            self._resources[name] = _ResourceEntry(
                resource=resource,
                cleanup_fn=cleanup_fn,
            )
            logger.debug("ResourceManager: registered '%s'", name)

    def unregister(self, name: str) -> None:
        """Remove a resource without cleaning it up.

        Parameters
        ----------
        name:
            Name of the resource to remove.
        """
        with self._lock:
            self._resources.pop(name, None)
            logger.debug("ResourceManager: unregistered '%s'", name)

    def get(self, name: str) -> Any | None:
        """Get a registered resource by name.

        Returns None if not found.
        """
        with self._lock:
            entry = self._resources.get(name)
            return entry.resource if entry is not None else None

    @contextmanager
    def acquire(self, name: str):
        """Context manager that yields a resource and cleans up on exit.

        Parameters
        ----------
        name:
            Name of the resource to acquire.

        Yields
        ------
        The registered resource.

        Raises
        ------
        KeyError
            If no resource is registered with this name.
        """
        with self._lock:
            entry = self._resources.get(name)
            if entry is None:
                raise KeyError(f"Resource '{name}' not registered")
            entry.acquired = True

        try:
            yield entry.resource
        finally:
            with self._lock:
                entry = self._resources.get(name)
                if entry is not None:
                    entry.acquired = False

    @asynccontextmanager
    async def async_acquire(self, name: str):
        """Async context manager that yields a resource.

        Parameters
        ----------
        name:
            Name of the resource to acquire.

        Yields
        ------
        The registered resource.

        Raises
        ------
        KeyError
            If no resource is registered with this name.
        """
        async with self._get_async_lock():
            entry = self._resources.get(name)
            if entry is None:
                raise KeyError(f"Resource '{name}' not registered")
            entry.acquired = True

        try:
            yield entry.resource
        finally:
            async with self._get_async_lock():
                entry = self._resources.get(name)
                if entry is not None:
                    entry.acquired = False

    async def shutdown_all(self) -> None:
        """Clean up all registered resources in reverse registration order.

        Supports both sync and async cleanup functions — the type is detected
        at call time. Errors during cleanup are logged but do not prevent
        subsequent resources from being cleaned up.
        """
        if self._shutdown_called:
            logger.debug("ResourceManager.shutdown_all: already called")
            return

        async with self._get_async_lock():
            self._shutdown_called = True
            names = list(reversed(list(self._resources.keys())))

        logger.info(
            "ResourceManager: shutting down %d resources in reverse order",
            len(names),
        )

        errors = []
        for name in names:
            async with self._get_async_lock():
                entry = self._resources.pop(name, None)

            if entry is None:
                continue

            try:
                if entry.cleanup_fn is not None:
                    result = entry.cleanup_fn()
                    if asyncio.iscoroutine(result):
                        await result
                logger.debug("ResourceManager: cleaned up '%s'", name)
            except Exception as exc:
                logger.warning(
                    "ResourceManager: cleanup failed for '%s': %s: %s",
                    name,
                    type(exc).__name__,
                    exc,
                )
                errors.append((name, exc))

        if errors:
            logger.warning(
                "ResourceManager: %d cleanup errors occurred", len(errors)
            )

    def _health_check(self) -> HealthResult:
        """Health check callback for the HealthRegistry."""
        if self._shutdown_called:
            return HealthResult(
                status=HealthStatus.DEGRADED,
                message="ResourceManager has been shut down",
            )

        with self._lock:
            count = len(self._resources)
            names = list(self._resources.keys())

        if count == 0:
            return HealthResult(
                status=HealthStatus.HEALTHY,
                message="No resources registered",
            )

        return HealthResult(
            status=HealthStatus.HEALTHY,
            message=f"{count} resource(s) registered",
            details={"resources": names, "count": count},
        )
