"""Feature registry — centralized feature discovery for brokers.

Provides a single source of truth for which features each broker supports.
This enables capability-based feature discovery without requiring direct
access to broker gateways.
"""

from __future__ import annotations

from brokers.domain.constants.capabilities import (
    FEATURE_ALERTS,
    FEATURE_AUTH,
    FEATURE_DEPTH200,
    FEATURE_EXIT_ALL,
    FEATURE_FOREVER_ORDERS,
    FEATURE_GTT,
    FEATURE_HISTORICAL,
    FEATURE_INSTRUMENTS,
    FEATURE_MARGIN_CALCULATOR,
    FEATURE_MARKET_DATA,
    FEATURE_MTF,
    FEATURE_NEWS,
    FEATURE_ORDERS,
    FEATURE_PORTFOLIO,
    FEATURE_SLICE_ORDERS,
    FEATURE_STREAMING,
    FEATURE_SUPER_ORDERS,
)


class FeatureRegistry:
    """Centralized feature registry for broker capability discovery.

    Maps broker IDs to their supported feature sets. New brokers
    register their features during initialization.
    """

    def __init__(self) -> None:
        self._features: dict[str, set[str]] = {}

    def register_broker(self, broker_id: str, features: set[str]) -> None:
        """Register features for a broker."""
        self._features[broker_id] = features.copy()

    def has_feature(self, broker_id: str, feature: str) -> bool:
        """Check if a broker supports a specific feature."""
        return feature in self._features.get(broker_id, set())

    def get_features(self, broker_id: str) -> frozenset[str]:
        """Get all features supported by a broker."""
        return frozenset(self._features.get(broker_id, set()))

    def get_brokers_with_feature(self, feature: str) -> list[str]:
        """Get all broker IDs that support a specific feature."""
        return [
            broker_id
            for broker_id, features in self._features.items()
            if feature in features
        ]


# Pre-configured feature sets for known brokers
DHAN_FEATURES: set[str] = {
    FEATURE_ORDERS,
    FEATURE_MARKET_DATA,
    FEATURE_PORTFOLIO,
    FEATURE_HISTORICAL,
    FEATURE_INSTRUMENTS,
    FEATURE_AUTH,
    FEATURE_STREAMING,
    FEATURE_GTT,
    FEATURE_SUPER_ORDERS,
    FEATURE_FOREVER_ORDERS,
    FEATURE_MARGIN_CALCULATOR,
    FEATURE_ALERTS,
    FEATURE_EXIT_ALL,
    FEATURE_MTF,
    FEATURE_SLICE_ORDERS,
    FEATURE_DEPTH200,
}

UPSTOX_FEATURES: set[str] = {
    FEATURE_ORDERS,
    FEATURE_MARKET_DATA,
    FEATURE_PORTFOLIO,
    FEATURE_HISTORICAL,
    FEATURE_INSTRUMENTS,
    FEATURE_AUTH,
    FEATURE_STREAMING,
    FEATURE_NEWS,
    FEATURE_GTT,
    FEATURE_DEPTH200,
}

PAPER_FEATURES: set[str] = {
    FEATURE_ORDERS,
    FEATURE_MARKET_DATA,
    FEATURE_PORTFOLIO,
    FEATURE_HISTORICAL,
    FEATURE_INSTRUMENTS,
    FEATURE_AUTH,
    FEATURE_STREAMING,
}


def create_default_registry() -> FeatureRegistry:
    """Create a feature registry with pre-configured broker features."""
    registry = FeatureRegistry()
    registry.register_broker("dhan", DHAN_FEATURES)
    registry.register_broker("upstox", UPSTOX_FEATURES)
    registry.register_broker("paper", PAPER_FEATURES)
    return registry
