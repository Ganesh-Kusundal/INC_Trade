"""Broker — deprecated alias for :class:`Platform`.

Kept for backward compatibility.  All ``Broker`` usage is forwarded
to :class:`Platform`.  New code should use ``Platform`` directly.
"""

from __future__ import annotations

import warnings
from typing import Any

from brokers.platform import Platform


class Broker:
    """Deprecated wrapper around Platform. All methods delegate to Platform."""

    __slots__ = ("_platform",)

    def __init__(
        self,
        provider_or_platform: Any = None,
        *,
        risk_policy: Any = None,
        event_bus: Any = None,
        **kwargs: Any,
    ) -> None:
        warnings.warn(
            "Broker is deprecated — use Platform instead",
            DeprecationWarning,
            stacklevel=2,
        )
        if isinstance(provider_or_platform, Platform):
            self._platform = provider_or_platform
        elif provider_or_platform is not None:
            # Legacy: Broker(provider, risk_policy=..., event_bus=...)
            self._platform = Platform(
                provider_or_platform,
                risk_policy=risk_policy,
                event_bus=event_bus,
                **kwargs,
            )
        else:
            raise TypeError("Broker requires a provider or Platform instance")

    @staticmethod
    def dhan(*args: Any, **kwargs: Any) -> Broker:
        warnings.warn("Broker is deprecated — use Platform instead", DeprecationWarning, stacklevel=2)
        b = Broker.__new__(Broker)
        b._platform = Platform.dhan(*args, **kwargs)
        return b

    @staticmethod
    def upstox(*args: Any, **kwargs: Any) -> Broker:
        warnings.warn("Broker is deprecated — use Platform instead", DeprecationWarning, stacklevel=2)
        b = Broker.__new__(Broker)
        b._platform = Platform.upstox(*args, **kwargs)
        return b

    @staticmethod
    def paper(*args: Any, **kwargs: Any) -> Broker:
        warnings.warn("Broker is deprecated — use Platform instead", DeprecationWarning, stacklevel=2)
        b = Broker.__new__(Broker)
        b._platform = Platform.paper(*args, **kwargs)
        return b

    @property
    def provider(self) -> Any:
        return self._platform.provider

    @property
    def broker_id(self) -> str:
        return self._platform.broker_id

    @property
    def is_connected(self) -> bool:
        return self._platform.is_connected

    def instrument(self, *args: Any, **kwargs: Any) -> Any:
        return self._platform.instrument(*args, **kwargs)

    def account(self) -> Any:
        return self._platform.account()

    async def connect(self) -> None:
        await self._platform.open()

    async def disconnect(self) -> None:
        await self._platform.disconnect()

    def __repr__(self) -> str:
        return f"Broker({self._platform.broker_id})"


__all__ = ["Broker"]
