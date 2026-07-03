"""Broker router — routes requests to the appropriate broker gateway.

This service provides capability-based routing and load balancing
across multiple broker gateways.
"""

from __future__ import annotations

import logging
from typing import Any

from brokers.ports.broker import BrokerGateway

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
        self._gateways: dict[str, BrokerGateway] = {}

    def register_gateway(self, broker_id: str, gateway: BrokerGateway) -> None:
        """Register a broker gateway.

        Args:
            broker_id: Unique broker identifier
            gateway: BrokerGateway instance
        """
        self._gateways[broker_id] = gateway
        logger.info("Registered broker gateway", extra={"broker_id": broker_id})

    def route(self, broker_id: str) -> BrokerGateway:
        """Route to a specific broker by ID.

        Args:
            broker_id: Broker identifier

        Returns:
            BrokerGateway instance

        Raises:
            ValueError: If broker not found
        """
        if broker_id not in self._gateways:
            raise ValueError(f"Broker {broker_id} not registered")
        return self._gateways[broker_id]

    def route_by_capability(self, capability: str) -> BrokerGateway | None:
        """Route to first broker that supports a capability.

        Args:
            capability: Capability constant (e.g., FEATURE_GTT)

        Returns:
            BrokerGateway instance if found, None otherwise
        """
        for gateway in self._gateways.values():
            if gateway.capabilities().has_feature(capability):
                return gateway
        return None

    def get_available_brokers(self) -> list[str]:
        """Get list of registered broker IDs.

        Returns:
            List of broker identifiers
        """
        return list(self._gateways.keys())

    def get_gateway(self, broker_id: str) -> BrokerGateway | None:
        """Get gateway by ID (non-strict version).

        Args:
            broker_id: Broker identifier

        Returns:
            BrokerGateway instance if found, None otherwise
        """
        return self._gateways.get(broker_id)
