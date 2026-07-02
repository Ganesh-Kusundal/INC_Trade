"""Runtime hooks registered at composition root (no broker imports in domain).

Module-level mutable globals replaced by frozen ``RuntimeHooks`` dataclass.
New code should use ``set_runtime_hooks(hooks)`` for dependency injection;
legacy ``register_*`` / ``create_*`` functions delegate to the module singleton
for backward compatibility.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any


@dataclass(frozen=True)
class RuntimeHooks:
    """Immutable container for runtime factory callables.

    Use :func:`set_runtime_hooks` to register all factories at once
    from the composition root. Legacy callers can continue using the
    individual ``register_*`` functions.
    """

    oms_backtest_factory: Callable[..., Any] | None = None
    domain_event_factory: Callable[..., Any] | None = None
    trading_context_factory: Callable[..., Any] | None = None


# ── Module singleton (backward-compatible) ──────────────────────────────
# All registrations happen at application startup; no concurrent callers.

_runtime_hooks = RuntimeHooks()


def set_runtime_hooks(hooks: RuntimeHooks) -> None:
    """Replace the module-level runtime hooks (preferred for DI)."""
    global _runtime_hooks
    _runtime_hooks = hooks


def register_oms_backtest_factory(factory: Callable[..., Any]) -> None:
    """Register factory used by analytics engines when ``trading_context`` is set."""
    global _runtime_hooks
    _runtime_hooks = replace(_runtime_hooks, oms_backtest_factory=factory)


def register_domain_event_factory(factory: Callable[..., Any]) -> None:
    """Register factory for creating domain events from analytics engines."""
    global _runtime_hooks
    _runtime_hooks = replace(_runtime_hooks, domain_event_factory=factory)


def register_trading_context_factory(factory: Callable[..., Any]) -> None:
    """Register factory for creating TradingContext from orchestrators."""
    global _runtime_hooks
    _runtime_hooks = replace(_runtime_hooks, trading_context_factory=factory)


def create_oms_backtest_adapter(trading_context: Any, **kwargs: Any) -> Any:
    """Create an OMS backtest adapter via the registered factory."""
    if _runtime_hooks.oms_backtest_factory is None:
        raise RuntimeError(
            "OMS backtest factory not registered. "
            "Call register_oms_backtest_factory() at application startup."
        )
    return _runtime_hooks.oms_backtest_factory(trading_context, **kwargs)


def create_domain_event(**kwargs: Any) -> Any:
    """Create a domain event via the registered factory."""
    if _runtime_hooks.domain_event_factory is None:
        raise RuntimeError("Domain event factory not registered.")
    return _runtime_hooks.domain_event_factory(**kwargs)


def create_trading_context(**kwargs: Any) -> Any:
    """Create a TradingContext via the registered factory."""
    if _runtime_hooks.trading_context_factory is None:
        raise RuntimeError(
            "Trading context factory not registered. "
            "Call register_trading_context_factory() at application startup."
        )
    return _runtime_hooks.trading_context_factory(**kwargs)


__all__ = [
    "RuntimeHooks",
    "create_domain_event",
    "create_oms_backtest_adapter",
    "create_trading_context",
    "register_domain_event_factory",
    "register_oms_backtest_factory",
    "register_trading_context_factory",
    "set_runtime_hooks",
]
