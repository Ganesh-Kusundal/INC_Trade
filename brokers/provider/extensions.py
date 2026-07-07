"""ExtensionAccess — typed, capability-gated access to broker extensions.

Replaces the old ``hasattr``/``getattr`` string-based dispatch and
``Any`` return types.  Extensions are typed Protocols.  The provider
declares support via capabilities.  Access via
``instrument.extensions.depth20`` returns typed extension or ``None``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from brokers.domain.instrument import Instrument
    from brokers.provider.protocol import Provider


# ── Typed extension protocols ──────────────────────────────────────────────


@runtime_checkable
class Depth20Extension(Protocol):
    """Dhan-specific 20-level depth extension."""

    async def get(self) -> Any:
        """Get the 20-level depth snapshot."""
        ...


@runtime_checkable
class Depth200Extension(Protocol):
    """Dhan-specific 200-level depth extension."""

    async def get(self) -> Any:
        """Get the 200-level depth snapshot."""
        ...


@runtime_checkable
class ForeverOrdersExtension(Protocol):
    """GTT/forever orders extension (Dhan and Upstox)."""

    async def place(self, **kwargs: Any) -> Any: ...
    async def cancel(self, order_id: str) -> Any: ...
    async def list(self) -> list[Any]: ...


@runtime_checkable
class SuperOrdersExtension(Protocol):
    """Dhan-specific super orders extension."""

    async def place(self, **kwargs: Any) -> Any: ...


@runtime_checkable
class MarginExtension(Protocol):
    """Margin calculation extension."""

    async def calculate(self, **kwargs: Any) -> Any: ...


@runtime_checkable
class ExitAllExtension(Protocol):
    """Exit all positions extension."""

    async def exit_all(self) -> Any: ...


# Registry of extension names → protocol types
_EXTENSION_PROTOCOLS: dict[str, type] = {
    "depth20": Depth20Extension,
    "depth200": Depth200Extension,
    "forever_orders": ForeverOrdersExtension,
    "super_orders": SuperOrdersExtension,
    "margin": MarginExtension,
    "exit_all": ExitAllExtension,
}


class ExtensionAccess:
    """Typed, capability-gated access to broker-specific extensions.

    Created by the provider.  Each extension property returns the typed
    extension object if the provider supports it, or ``None`` if not.

    Usage::

        depth20 = instrument.extensions.depth20
        if depth20:
            snapshot = await depth20.get()
    """

    __slots__ = ("_extensions", "_instrument", "_provider")

    def __init__(
        self,
        provider: Provider,
        instrument: Instrument | None = None,
        *,
        extensions: dict[str, Any] | None = None,
    ) -> None:
        self._provider = provider
        self._instrument = instrument
        # extensions is a dict of name → extension instance
        self._extensions = extensions or {}

    # ── Typed extension accessors ────────────────────────────────────

    @property
    def depth20(self) -> Depth20Extension | None:
        """Dhan 20-level depth, or None if not supported."""
        return self._extensions.get("depth20")

    @property
    def depth200(self) -> Depth200Extension | None:
        """Dhan 200-level depth, or None if not supported."""
        return self._extensions.get("depth200")

    @property
    def forever_orders(self) -> ForeverOrdersExtension | None:
        """GTT/forever orders, or None if not supported."""
        return self._extensions.get("forever_orders")

    @property
    def super_orders(self) -> SuperOrdersExtension | None:
        """Dhan super orders, or None if not supported."""
        return self._extensions.get("super_orders")

    @property
    def margin(self) -> MarginExtension | None:
        """Margin calculation, or None if not supported."""
        return self._extensions.get("margin")

    @property
    def exit_all(self) -> ExitAllExtension | None:
        """Exit all positions, or None if not supported."""
        return self._extensions.get("exit_all")

    # ── Generic access ───────────────────────────────────────────────

    def get(self, name: str) -> Any | None:
        """Generic extension lookup by name."""
        return self._extensions.get(name)

    def has(self, name: str) -> bool:
        """Check if an extension is available."""
        return name in self._extensions

    @property
    def available(self) -> list[str]:
        """List of available extension names."""
        return list(self._extensions.keys())

    # ── Factory ──────────────────────────────────────────────────────

    def for_instrument(self, instrument: Instrument) -> ExtensionAccess:
        """Create a new ExtensionAccess scoped to a specific instrument."""
        return ExtensionAccess(
            self._provider,
            instrument,
            extensions=self._extensions,
        )


__all__ = [
    "Depth20Extension",
    "Depth200Extension",
    "ExitAllExtension",
    "ExtensionAccess",
    "ForeverOrdersExtension",
    "MarginExtension",
    "SuperOrdersExtension",
]
