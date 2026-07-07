"""ExtensionAccess — typed, capability-gated access to broker extensions.

Replaces the old ``hasattr``/``getattr`` string-based dispatch and
``Any`` return types.  Extensions are typed Protocols.  The provider
declares support via capabilities.  Access via
``instrument.extensions.depth20`` returns a typed extension or ``None``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, TypeVar, overload, runtime_checkable

T = TypeVar("T")

if TYPE_CHECKING:
    from brokers.domain.capabilities import Capability
    from brokers.domain.instrument import Instrument
    from brokers.provider.protocol import Provider

from brokers.domain.capabilities import Capability


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


@runtime_checkable
class GenericExtension(Protocol):
    """Permissive protocol used when no dedicated Protocol is defined.

    A runtime-checkable Protocol with no methods matches every object, so
    registration is validated by capability gating alone for these names.
    """


# Registry: extension name → Protocol used to validate the registered object.
# This is the canonical place that ensures a registered object actually
# conforms to the expected Protocol before a typed accessor returns it.
_EXTENSION_PROTOCOLS: dict[str, type] = {
    "depth20": Depth20Extension,
    "depth200": Depth200Extension,
    "forever_orders": ForeverOrdersExtension,
    "super_orders": SuperOrdersExtension,
    "margin": MarginExtension,
    "exit_all": ExitAllExtension,
    # Named extensions without a dedicated Protocol — validated permissively.
    "gtt": GenericExtension,
    "cover": GenericExtension,
    "slice": GenericExtension,
    "ip_management": GenericExtension,
    "ledger": GenericExtension,
    "edis": GenericExtension,
    "alerts": GenericExtension,
    "kill_switch": GenericExtension,
    "market_intelligence": GenericExtension,
    "news": GenericExtension,
    "fundamentals": GenericExtension,
    "static_ip": GenericExtension,
    "mutual_funds": GenericExtension,
    "payments": GenericExtension,
    "order_query": GenericExtension,
    "reconciliation": GenericExtension,
}

# Registry: extension name → Capability that must be supported for the
# extension to be exposed.  ``None`` means no corresponding Capability exists
# in the domain model, so the accessor is not capability-gated (it is still
# Protocol-validated via ``_EXTENSION_PROTOCOLS``).
_EXTENSION_CAPABILITY: dict[str, Capability | None] = {
    "depth20": Capability.DEPTH_20,
    # No DEPTH_200 capability exists; DEPTH_30 is the closest depth tier.
    "depth200": Capability.DEPTH_30,
    "super_orders": Capability.SUPER_ORDERS,
    "forever_orders": Capability.FOREVER_ORDERS,
    "gtt": Capability.GTT_ORDERS,
    "cover": Capability.COVER_ORDERS,
    "slice": Capability.SLICE_ORDERS,
    "margin": Capability.MARGIN_CALCULATION,
    "exit_all": Capability.EXIT_ALL,
    "ledger": Capability.LEDGER,
    "edis": Capability.EDIS,
    "alerts": Capability.ALERTS,
    "market_intelligence": Capability.MARKET_INTELLIGENCE,
    "news": Capability.NEWS,
    "fundamentals": Capability.FUNDAMENTALS,
    # No STATIC_IP capability exists in the domain model — not gated.
    "static_ip": None,
    # ip_management (client IP whitelisting) has no dedicated capability —
    # there is no STATIC_IP capability either, so it is not gated.
    "ip_management": None,
    "mutual_funds": Capability.MUTUAL_FUNDS,
    # No capability exists for these in the domain model — not gated.
    "kill_switch": None,
    "payments": None,
    "order_query": None,
    "reconciliation": None,
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
        extensions: dict[str, Any] | None = None,
        *,
        instrument: Instrument | None = None,
    ) -> None:
        self._provider = provider
        self._instrument = instrument
        # extensions is a dict of name → extension instance
        self._extensions = extensions or {}

    # ── Internal access helper ─────────────────────────────────────────

    def _access(self, name: str) -> Any | None:
        """Capability-gate + Protocol-validate a registered extension."""
        cap = _EXTENSION_CAPABILITY.get(name)
        if cap is not None and not self._provider.capabilities.supports(cap):
            return None
        obj = self._extensions.get(name)
        if obj is None:
            return None
        protocol = _EXTENSION_PROTOCOLS.get(name, GenericExtension)
        if not isinstance(obj, protocol):
            return None
        return obj

    # ── Typed extension accessors ────────────────────────────────────

    @property
    def depth20(self) -> Depth20Extension | None:
        """Dhan 20-level depth, or None if not supported."""
        return self._access("depth20")  # type: ignore[return-value]

    @property
    def depth200(self) -> Depth200Extension | None:
        """Dhan 200-level depth, or None if not supported."""
        return self._access("depth200")  # type: ignore[return-value]

    @property
    def forever_orders(self) -> ForeverOrdersExtension | None:
        """GTT/forever orders, or None if not supported."""
        return self._access("forever_orders")  # type: ignore[return-value]

    @property
    def super_orders(self) -> SuperOrdersExtension | None:
        """Dhan super orders, or None if not supported."""
        return self._access("super_orders")  # type: ignore[return-value]

    @property
    def margin(self) -> MarginExtension | None:
        """Margin calculation, or None if not supported."""
        return self._access("margin")  # type: ignore[return-value]

    @property
    def exit_all(self) -> ExitAllExtension | None:
        """Exit all positions, or None if not supported."""
        return self._access("exit_all")  # type: ignore[return-value]

    @property
    def gtt(self) -> Any | None:
        """GTT orders, or None if not supported."""
        return self._access("gtt")

    @property
    def cover(self) -> Any | None:
        """Cover orders, or None if not supported."""
        return self._access("cover")

    @property
    def slice(self) -> Any | None:
        """Slice orders, or None if not supported."""
        return self._access("slice")

    @property
    def ip_management(self) -> Any | None:
        """IP whitelisting management, or None if not supported."""
        return self._access("ip_management")

    @property
    def ledger(self) -> Any | None:
        """Ledger access, or None if not supported."""
        return self._access("ledger")

    @property
    def edis(self) -> Any | None:
        """EDIS (e-disclosure) access, or None if not supported."""
        return self._access("edis")

    @property
    def alerts(self) -> Any | None:
        """Alerts, or None if not supported."""
        return self._access("alerts")

    @property
    def kill_switch(self) -> Any | None:
        """Kill switch, or None if not supported."""
        return self._access("kill_switch")

    @property
    def market_intelligence(self) -> Any | None:
        """Market intelligence, or None if not supported."""
        return self._access("market_intelligence")

    @property
    def news(self) -> Any | None:
        """News, or None if not supported."""
        return self._access("news")

    @property
    def fundamentals(self) -> Any | None:
        """Fundamentals, or None if not supported."""
        return self._access("fundamentals")

    @property
    def static_ip(self) -> Any | None:
        """Static IP management, or None if not supported."""
        return self._access("static_ip")

    @property
    def mutual_funds(self) -> Any | None:
        """Mutual funds, or None if not supported."""
        return self._access("mutual_funds")

    @property
    def payments(self) -> Any | None:
        """Payments, or None if not supported."""
        return self._access("payments")

    @property
    def order_query(self) -> Any | None:
        """Order query, or None if not supported."""
        return self._access("order_query")

    @property
    def reconciliation(self) -> Any | None:
        """Reconciliation, or None if not supported."""
        return self._access("reconciliation")

    # ── Generic access ───────────────────────────────────────────────

    @overload
    def get(self, name: str) -> Any | None: ...
    @overload
    def get(self, name: str, type: type[T]) -> T | None: ...

    def get(self, name: str, type: type[T] | None = None) -> Any | None:
        """Generic extension lookup by name.

        When ``type`` is provided, the returned object is validated against
        it with ``isinstance`` — the call returns ``None`` if the registered
        object is not an instance of ``type`` (the previous cast was a lie).
        Capability gating is applied when a capability is registered for the
        name.
        """
        cap = _EXTENSION_CAPABILITY.get(name)
        if cap is not None and not self._provider.capabilities.supports(cap):
            return None
        obj = self._extensions.get(name)
        if obj is None:
            return None
        if type is not None and not isinstance(obj, type):
            return None
        return obj

    def has(self, name: str) -> bool:
        """Check if an extension is available."""
        return name in self._extensions

    @property
    def available(self) -> list[str]:
        """List of available extension names."""
        return list(self._extensions.keys())

    @property
    def registered(self) -> dict[str, Any]:
        """Read-only view of the registered name → extension dict.

        Used by CompositeProvider to merge sub-provider extensions.  Callers
        must NOT mutate the returned dict.
        """
        return self._extensions

    # ── Factory ──────────────────────────────────────────────────────

    def for_instrument(self, instrument: Instrument) -> ExtensionAccess:
        """Create a new ExtensionAccess scoped to a specific instrument."""
        return ExtensionAccess(
            self._provider,
            self._extensions,
            instrument=instrument,
        )


__all__ = [
    "Depth20Extension",
    "Depth200Extension",
    "ExitAllExtension",
    "ExtensionAccess",
    "ForeverOrdersExtension",
    "GenericExtension",
    "MarginExtension",
    "SuperOrdersExtension",
]
