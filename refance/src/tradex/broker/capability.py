"""Capability registry — broker capability discovery and matching."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class BrokerCapability:
    """A single broker capability."""

    name: str
    description: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    required: bool = False

    def __hash__(self) -> int:
        return hash(self.name)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, BrokerCapability):
            return self.name == other.name
        return NotImplemented


class CapabilityRegistry:
    """Registry of capabilities supported by a broker.

    Capabilities are dynamically discovered. No broker-specific
    conditionals in core code.
    """

    def __init__(self) -> None:
        self._capabilities: dict[str, BrokerCapability] = {}

    def register(self, capability: BrokerCapability) -> None:
        """Register a capability."""
        self._capabilities[capability.name] = capability

    def register_many(self, capabilities: list[BrokerCapability]) -> None:
        """Register multiple capabilities."""
        for cap in capabilities:
            self.register(cap)

    def has(self, name: str) -> bool:
        """Check if a capability is registered."""
        return name in self._capabilities

    def get(self, name: str) -> Optional[BrokerCapability]:
        """Get a capability by name."""
        return self._capabilities.get(name)

    def get_parameter(self, name: str, param: str, default: Any = None) -> Any:
        """Get a parameter from a capability."""
        cap = self.get(name)
        if cap:
            return cap.parameters.get(param, default)
        return default

    @property
    def all(self) -> list[BrokerCapability]:
        """All registered capabilities."""
        return list(self._capabilities.values())

    @property
    def names(self) -> list[str]:
        """All capability names."""
        return list(self._capabilities.keys())

    def __len__(self) -> int:
        return len(self._capabilities)

    def __contains__(self, name: str) -> bool:
        return name in self._capabilities


# --- Well-known capability names ---


class CapabilityNames:
    """Standard capability names across brokers."""

    SUPER_ORDERS = "super_orders"
    FOREVER_ORDERS = "forever_orders"
    DEPTH_20 = "depth_20"
    DEPTH_200 = "depth_200"
    SLICE_ORDERS = "slice_orders"
    EDIS = "edis"
    KILL_SWITCH = "kill_switch"
    MARGIN_CALCULATOR = "margin_calculator"
    TRADE_HISTORY = "trade_history"
    LEDGER_REPORT = "ledger_report"
    POSITION_CONVERSION = "position_conversion"
    AFTER_MARKET_ORDER = "after_market_order"
    BRACKET_ORDER = "bracket_order"
    COVER_ORDER = "cover_order"
