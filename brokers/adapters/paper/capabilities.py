"""Paper trading capabilities."""

from brokers.domain.constants.capabilities import (
    FEATURE_AUTH,
    FEATURE_HISTORICAL,
    FEATURE_INSTRUMENTS,
    FEATURE_MARKET_DATA,
    FEATURE_ORDERS,
    FEATURE_PORTFOLIO,
    FEATURE_STREAMING,
)
from brokers.ports.capabilities import Capabilities


class PaperCapabilities(Capabilities):
    """Capabilities for paper trading gateway."""

    def has_feature(self, feature: str) -> bool:
        """Check if paper trading supports a feature."""
        return feature in {
            FEATURE_ORDERS,
            FEATURE_MARKET_DATA,
            FEATURE_PORTFOLIO,
            FEATURE_HISTORICAL,
            FEATURE_INSTRUMENTS,
            FEATURE_AUTH,
            FEATURE_STREAMING,
        }

    def get_feature_metadata(self, feature: str) -> dict:
        """Get metadata about a paper trading feature."""
        metadata = {
            FEATURE_ORDERS: {
                "description": "Order placement (simulated)",
                "supported_exchanges": ["NSE", "BSE"],
                "limitations": ["Simulated only, no real execution"],
            },
            FEATURE_MARKET_DATA: {
                "description": "Market data (simulated)",
                "supported_exchanges": ["NSE", "BSE"],
                "limitations": ["Static quotes, no real-time data"],
            },
            FEATURE_PORTFOLIO: {
                "description": "Portfolio tracking (simulated)",
                "supported_exchanges": ["NSE", "BSE"],
                "limitations": ["In-memory only, no persistence"],
            },
            FEATURE_HISTORICAL: {
                "description": "Historical data (empty)",
                "supported_exchanges": ["NSE", "BSE"],
                "limitations": ["Returns empty data"],
            },
            FEATURE_INSTRUMENTS: {
                "description": "Instrument search (basic)",
                "supported_exchanges": ["NSE", "BSE"],
                "limitations": ["Limited instrument master"],
            },
            FEATURE_AUTH: {
                "description": "Authentication (always succeeds)",
                "supported_exchanges": [],
                "limitations": ["No real authentication"],
            },
            FEATURE_STREAMING: {
                "description": "Streaming (no-op)",
                "supported_exchanges": [],
                "limitations": ["No real streaming"],
            },
        }
        return metadata.get(
            feature,
            {
                "description": "Unknown feature",
                "supported_exchanges": [],
                "limitations": ["Not supported by paper trading"],
            },
        )


def paper_capabilities() -> Capabilities:
    """Factory for paper trading capabilities."""
    return PaperCapabilities()
