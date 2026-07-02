"""Canonical status mapper registry — centralized status string → OrderStatus mapping.

All broker-specific status mappers register their mappings at import time.
``OrderStatus.normalize()`` delegates to this registry, ensuring a single
source of truth for status normalization across the entire codebase.
"""

from __future__ import annotations

from typing import ClassVar

from domain.types import OrderStatus


class UnmappedBrokerStatusError(ValueError):
    """Raised when a broker status string cannot be mapped to OrderStatus."""

    def __init__(self, broker_status: str) -> None:
        super().__init__(f"Unmapped broker order status: {broker_status!r}")
        self.broker_status = broker_status


class StatusMapperRegistry:
    """Global registry for broker-specific status mappings.

    Broker adapters register their mappings at module import time by calling
    ``register(broker_name, mapping_dict)``. The registry merges all mappings
    and provides a single ``normalize()`` method that tries all registered
    mappings in order, returning ``OrderStatus.UNKNOWN`` for unmapped statuses.
    """

    _mappings: ClassVar[dict[str, dict[str, OrderStatus]]] = {}
    _merged: ClassVar[dict[str, OrderStatus] | None] = None

    @classmethod
    def register(cls, broker_name: str, mapping: dict[str, OrderStatus]) -> None:
        """Register a broker-specific status mapping.

        Args:
            broker_name: Unique identifier for the broker (e.g., 'dhan', 'upstox')
            mapping: Dict mapping status strings to OrderStatus enums
        """
        cls._mappings[broker_name] = mapping
        cls._merged = None  # Invalidate cache

    @classmethod
    def normalize(cls, broker_status: str) -> OrderStatus:
        """Normalize a broker-specific status string to canonical OrderStatus.

        Tries all registered mappings in order. Returns UNKNOWN for unmapped statuses.

        Args:
            broker_status: Raw status string from broker API

        Returns:
            Canonical OrderStatus enum value (UNKNOWN when unmapped)
        """
        normalized = broker_status.upper().strip().replace(" ", "_")
        if not normalized:
            return OrderStatus.UNKNOWN
        if cls._merged is None:
            cls._merged = {}
            for mapping in cls._mappings.values():
                cls._merged.update(mapping)
        if normalized in cls._merged:
            return cls._merged[normalized]
        try:
            return OrderStatus(normalized)
        except ValueError:
            return OrderStatus.UNKNOWN

    @classmethod
    def normalize_strict(cls, broker_status: str) -> OrderStatus:
        """Like ``normalize`` but raises :class:`UnmappedBrokerStatusError` when unmapped."""
        result = cls.normalize(broker_status)
        if result is OrderStatus.UNKNOWN:
            raise UnmappedBrokerStatusError(broker_status)
        return result


# ── Common status map (backward compatibility) ────────────────────────────

COMMON_STATUS_MAP: dict[str, OrderStatus] = {
    # ── Canonical identity mappings (so normalize("FILLED") returns FILLED) ──
    "OPEN": OrderStatus.OPEN,
    "PARTIALLY_FILLED": OrderStatus.PARTIALLY_FILLED,
    "FILLED": OrderStatus.FILLED,
    "CANCELLED": OrderStatus.CANCELLED,
    "PARTIALLY_CANCELLED": OrderStatus.PARTIALLY_CANCELLED,
    "REJECTED": OrderStatus.REJECTED,
    "EXPIRED": OrderStatus.EXPIRED,
    "UNKNOWN": OrderStatus.UNKNOWN,
    # ── Terminal / filled ──
    "EXECUTED": OrderStatus.FILLED,
    "COMPLETE": OrderStatus.FILLED,
    "COMPLETED": OrderStatus.FILLED,
    "TRADED": OrderStatus.FILLED,
    # ── Partial fills ──
    "PARTIAL": OrderStatus.PARTIALLY_FILLED,
    "PARTIALLY_EXECUTED": OrderStatus.PARTIALLY_FILLED,
    "MARGIN_TRADED": OrderStatus.PARTIALLY_FILLED,
    # ── Open / pending ──
    "AFTER_MARKET_ORDER_REQ_RECEIVED": OrderStatus.OPEN,
    "AMO": OrderStatus.OPEN,
    "TRANSIT": OrderStatus.OPEN,
    "TRIGGER_PENDING": OrderStatus.OPEN,
    "PENDING": OrderStatus.OPEN,
    "QUEUED": OrderStatus.OPEN,
    "PUT_ORDER_REQ_RECEIVED": OrderStatus.OPEN,
    "OPEN_PENDING": OrderStatus.OPEN,
}

# Register common mappings at module load
StatusMapperRegistry.register("common", COMMON_STATUS_MAP)
