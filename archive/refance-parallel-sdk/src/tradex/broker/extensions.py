"""Broker extension framework — optional capabilities discovered at runtime."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from tradex.broker.capability import CapabilityRegistry


class BrokerExtension(ABC):
    """Base class for broker extensions.

    Extensions are optional features provided by specific brokers.
    They are discovered dynamically via the capability registry.
    No broker-specific conditionals in core code.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Extension name (must match a capability name)."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description."""

    @abstractmethod
    async def execute(self, **kwargs: Any) -> Any:
        """Execute the extension with given parameters."""

    async def validate(self, **kwargs: Any) -> bool:
        """Validate that the extension can execute with given parameters."""
        return True


class ExtensionRegistry:
    """Registry of broker extensions.

    Extensions register by name. Users discover and invoke them.
    No if/else on broker names anywhere.
    """

    def __init__(self, capabilities: CapabilityRegistry) -> None:
        self._capabilities = capabilities
        self._extensions: dict[str, BrokerExtension] = {}

    def register(self, extension: BrokerExtension) -> None:
        """Register an extension."""
        self._extensions[extension.name] = extension

    def get(self, name: str) -> Optional[BrokerExtension]:
        """Get an extension by name."""
        ext = self._extensions.get(name)
        if ext and self._capabilities.has(name):
            return ext
        return None

    async def execute(self, name: str, **kwargs: Any) -> Any:
        """Execute an extension by name."""
        ext = self.get(name)
        if ext is None:
            raise ValueError(f"Extension '{name}' not found or not supported by this broker")

        if not await ext.validate(**kwargs):
            raise ValueError(f"Extension '{name}' validation failed for given parameters")

        return await ext.execute(**kwargs)

    @property
    def available(self) -> list[str]:
        """List available extension names."""
        return [name for name in self._extensions if self._capabilities.has(name)]

    def __contains__(self, name: str) -> bool:
        return self.get(name) is not None
