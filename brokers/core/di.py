"""Lightweight Dependency Injection Container.

Provides a thread-safe DI container with support for:
- singleton: created once, shared across all resolutions
- transient: new instance each time
- request: one instance per request scope (via contextvar)

Usage:
    from brokers.core.di import container, Scope

    container.register("my_service", lambda: MyService(), scope=Scope.SINGLETON)
    container.register("repo", OrderRepository, scope=Scope.TRANSIENT)
    container.register_instance("config", config_object)

    service = container.resolve("my_service")
"""

from __future__ import annotations

import enum
import logging
import threading
from collections.abc import Callable
from typing import Any

from brokers.core.di_scopes import ScopeManager

logger = logging.getLogger(__name__)


class Scope(enum.Enum):
    """Service lifetime scopes."""

    SINGLETON = "singleton"
    TRANSIENT = "transient"
    REQUEST = "request"


_VALID_SCOPES = {s.value for s in Scope}


class CircularDependencyError(Exception):
    """Raised when a circular dependency is detected during resolution."""


class ServiceNotFoundError(Exception):
    """Raised when resolving a service that is not registered."""


class Container:
    """Thread-safe dependency injection container.

    Supports three scopes:
    - singleton: Factory called once, result cached forever
    - transient: Factory called on every resolve()
    - request: Factory called once per request_scope() context manager
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._factories: dict[str, Callable[[], Any]] = {}
        self._scopes: dict[str, str] = {}
        self._singletons: dict[str, Any] = {}
        self._scope_manager = ScopeManager()
        self._resolving: set[str] = set()

    def register(
        self,
        name: str,
        factory: Callable[[], Any] | type,
        scope: str | Scope = Scope.SINGLETON,
    ) -> None:
        """Register a service factory.

        Parameters
        ----------
        name:
            Unique identifier for the service.
        factory:
            Callable that returns a service instance (class or lambda).
        scope:
            A Scope enum value or one of 'singleton', 'transient', 'request'.

        Raises
        ------
        ValueError
            If scope is not one of the allowed values.
        """
        scope_str = scope.value if isinstance(scope, Scope) else scope
        if scope_str not in _VALID_SCOPES:
            raise ValueError(
                f"Invalid scope '{scope_str}'. Must be 'singleton', 'transient', or 'request'."
            )

        with self._lock:
            self._factories[name] = factory
            self._scopes[name] = scope_str
            self._singletons.pop(name, None)
            logger.debug("Registered service '%s' with scope '%s'", name, scope_str)

    def register_instance(self, name: str, instance: Any) -> None:
        """Register a pre-created instance as a singleton."""
        with self._lock:
            self._singletons[name] = instance
            self._factories.pop(name, None)
            self._scopes[name] = "instance"
            logger.debug("Registered instance '%s'", name)

    def resolve(self, name: str) -> Any:
        """Resolve a service by name.

        Raises
        ------
        ServiceNotFoundError
            If the service is not registered.
        CircularDependencyError
            If a circular dependency is detected.
        """
        # Fast path: cached singletons (read without lock)
        if name in self._singletons:
            return self._singletons[name]

        with self._lock:
            factory = self._factories.get(name)
            scope = self._scopes.get(name, "singleton")

        if factory is None and name not in self._singletons:
            raise ServiceNotFoundError(f"Service '{name}' is not registered.")

        if scope == "singleton":
            return self._resolve_singleton(name, factory)  # type: ignore[arg-type]
        elif scope == "transient":
            return self._resolve_transient(name, factory)  # type: ignore[arg-type]
        elif scope == "request":
            return self._resolve_request(name, factory)  # type: ignore[arg-type]
        else:
            # instance scope
            return self._singletons[name]

    def _resolve_singleton(self, name: str, factory: Callable[[], Any]) -> Any:
        """Resolve a singleton service."""
        with self._lock:
            if name in self._singletons:
                return self._singletons[name]

            if name in self._resolving:
                raise CircularDependencyError(
                    f"Circular dependency detected while resolving '{name}'"
                )
            self._resolving.add(name)

        try:
            instance = factory()
        except CircularDependencyError:
            raise
        except Exception:
            raise
        finally:
            with self._lock:
                self._resolving.discard(name)

        with self._lock:
            self._singletons[name] = instance
        return instance

    def _resolve_transient(self, name: str, factory: Callable[[], Any]) -> Any:
        """Resolve a transient service (new instance each time)."""
        with self._lock:
            if name in self._resolving:
                raise CircularDependencyError(
                    f"Circular dependency detected while resolving '{name}'"
                )
            self._resolving.add(name)

        try:
            return factory()
        except CircularDependencyError:
            raise
        except Exception:
            raise
        finally:
            with self._lock:
                self._resolving.discard(name)

    def _resolve_request(self, name: str, factory: Callable[[], Any]) -> Any:
        """Resolve a request-scoped service."""
        return self._scope_manager.resolve(name, factory)

    def reset(self) -> None:
        """Clear all registrations and cached instances. Useful for testing."""
        with self._lock:
            self._factories.clear()
            self._scopes.clear()
            self._singletons.clear()
            self._scope_manager.clear()
            self._resolving.clear()
            logger.debug("Container reset")

    def has(self, name: str) -> bool:
        """Check if a service is registered."""
        return name in self._factories or name in self._singletons

    def registrations(self) -> dict[str, str]:
        """Get a summary of registered services and their scopes."""
        result: dict[str, str] = {}
        with self._lock:
            result.update(self._scopes)
        return result


# Module-level singleton container
container = Container()
