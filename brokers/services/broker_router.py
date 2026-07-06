"""Broker router — routes requests to the appropriate broker gateway.

This service provides capability-based routing and load balancing
across multiple broker gateways.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class BrokerRouter:
    """Route requests to broker gateways based on capability and preference.

    Maintains a registry of available broker gateways and routes requests
    to the most appropriate broker based on:
    - Required capabilities
    - Broker preference
    - Load balancing
    """

    def __init__(self) -> None:
        """Initialize with empty gateway registry."""
        self._gateways: dict[str, Any] = {}

    def register_gateway(self, broker_id: str, gateway: Any) -> None:
        """Register a broker gateway.

        Args:
            broker_id: Unique broker identifier
            gateway: Any instance
        """
        self._gateways[broker_id] = gateway
        logger.info("Registered broker gateway", extra={"broker_id": broker_id})

    def route(self, broker_id: str) -> Any:
        """Route to a specific broker by ID.

        Args:
            broker_id: Broker identifier

        Returns:
            Gateway instance

        Raises:
            ValueError: If broker not found
        """
        if broker_id not in self._gateways:
            raise ValueError(f"Broker {broker_id} not registered")
        return self._gateways[broker_id]

    def route_by_capability(self, capability: str) -> Any | None:
        """Route to first broker that supports a capability.

        Args:
            capability: Capability string (e.g., ``"orders"`` or feature constant)

        Returns:
            Any instance if found, None otherwise
        """
        for gateway in self._gateways.values():
            caps = gateway.capabilities()
            if hasattr(caps, "supports") and caps.supports(capability):
                return gateway
            if hasattr(caps, "has_feature") and caps.has_feature(capability):
                return gateway
        return None

    def get_available_brokers(self) -> list[str]:
        """Get list of registered broker IDs.

        Returns:
            List of broker identifiers
        """
        return list(self._gateways.keys())

    def get_gateway(self, broker_id: str) -> Any | None:
        """Get gateway by ID (non-strict version).

        Args:
            broker_id: Broker identifier

        Returns:
            Any instance if found, None otherwise
        """
        return self._gateways.get(broker_id)
