"""Request-scoped dependency management using contextvars.

Provides per-request lifetime management for services registered
with scope='request'. Each request_scope() context manager creates
a new scope, and services within that scope are created once and
shared across all resolutions within the same request.

Usage:
    from infrastructure.di_scopes import request_scope

    async def handle_request():
        async with request_scope():
            # Services resolved here are request-scoped
            svc1 = container.resolve("my_service")
            svc2 = container.resolve("my_service")
            assert svc1 is svc2  # Same instance within request

    # Outside request_scope(), request-scoped services raise errors
"""

from __future__ import annotations

import contextvars
import threading
from collections.abc import Callable
from contextlib import contextmanager
from typing import Any

from domain.exceptions import TradeXV2Error

# Context variable for the current request scope
_current_scope: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "di_request_scope", default=None
)


class NoActiveRequestScope(TradeXV2Error):
    """Raised when resolving a request-scoped service outside a request_scope()."""


class ScopeManager:
    """Manages request-scoped service instances.

    Uses contextvars to ensure each request gets its own isolated
    set of service instances. Thread-safe via contextvars semantics.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._factories: dict[str, Callable[[], Any]] = {}

    def resolve(self, name: str, factory: Callable[[], Any]) -> Any:
        """Resolve a request-scoped service.

        Parameters
        ----------
        name:
            The service identifier.
        factory:
            Callable that creates the service instance.

        Returns
        -------
        The service instance, created once per request scope.

        Raises
        ------
        NoActiveRequestScope
            If called outside a request_scope() context.
        """
        scope = _current_scope.get()
        if scope is None:
            raise NoActiveRequestScope(
                f"Cannot resolve request-scoped service '{name}' "
                f"outside of a request_scope() context manager."
            )

        # Return cached instance if already created in this scope
        if name in scope:
            return scope[name]

        # Create and cache the instance
        instance = factory()
        scope[name] = instance
        return instance

    def clear(self) -> None:
        """Clear any cached factory references."""
        with self._lock:
            self._factories.clear()


@contextmanager
def request_scope():
    """Context manager that creates a new request scope.

    Services registered with scope='request' are created once
    within this scope and shared across all resolutions.

    Usage:
        with request_scope():
            svc = container.resolve("my_service")
            # svc is request-scoped

    Raises
    ------
    None
    """
    # Create a new scope dict
    scope: dict[str, Any] = {}
    token = _current_scope.set(scope)
    try:
        yield scope
    finally:
        _current_scope.reset(token)


@contextmanager
def get_request_scope() -> dict[str, Any] | None:
    """Get the current request scope without creating a new one.

    Returns the current scope dict if inside a request_scope(),
    or None if outside.

    Usage:
        with get_request_scope() as scope:
            if scope is not None:
                # Inside request scope
                pass
    """
    yield _current_scope.get()


def has_request_scope() -> bool:
    """Check if currently inside a request scope.

    Returns
    -------
    True if inside a request_scope() context manager, False otherwise.
    """
    return _current_scope.get() is not None
