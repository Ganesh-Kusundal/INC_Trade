"""Capability discovery — find brokers that support specific features.

This service provides a high-level API for discovering which brokers
support which capabilities, enabling broker-agnostic client code.
"""

from __future__ import annotations

import logging
from typing import Any

from brokers.ports.broker import BrokerGateway
from brokers.ports.capabilities import Capabilities
from brokers.services.broker_router import BrokerRouter

logger = logging.getLogger(__name__)


class CapabilityDiscovery:
    """Discover broker capabilities and retrieve extension providers.

    Provides a unified interface for checking feature support and
    retrieving typed extension instances from broker gateways.
    """

    def __init__(self, router: BrokerRouter):
        """Initialize with a broker router.

        Args:
            router: BrokerRouter instance for accessing gateways
        """
        self._router = router

    def has_feature(self, broker_id: str, feature: str) -> bool:
        """Check if a broker supports a feature.

        Args:
            broker_id: Broker identifier
            feature: Capability constant (e.g., FEATURE_GTT)

        Returns:
            True if supported, False otherwise
        """
        try:
            gateway = self._router.route(broker_id)
            return gateway.capabilities().has_feature(feature)
        except ValueError:
            return False

    def get_extension(self, broker_id: str, extension_type: type[Any]) -> Any | None:
        """Get a typed extension from a broker.

        Args:
            broker_id: Broker identifier
            extension_type: Extension protocol type

        Returns:
            Extension instance if available, None otherwise
        """
        try:
            gateway = self._router.route(broker_id)
            return gateway.extensions.get_extension(extension_type)
        except ValueError:
            return None

    def find_brokers_with_feature(self, feature: str) -> list[str]:
        """Find all brokers that support a feature.

        Args:
            feature: Capability constant

        Returns:
            List of broker IDs that support the feature
        """
        brokers = []
        for broker_id in self._router.get_available_brokers():
            if self.has_feature(broker_id, feature):
                brokers.append(broker_id)
        return brokers

    def get_feature_metadata(self, broker_id: str, feature: str) -> dict[str, Any]:
        """Get metadata about a broker's feature.

        Args:
            broker_id: Broker identifier
            feature: Capability constant

        Returns:
            Metadata dictionary
        """
        try:
            gateway = self._router.route(broker_id)
            return gateway.capabilities().get_feature_metadata(feature)
        except ValueError:
            return {
                "description": "Unknown feature",
                "supported_exchanges": [],
                "limitations": ["Broker not found"],
            }
