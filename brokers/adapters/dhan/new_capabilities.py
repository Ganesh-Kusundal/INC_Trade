"""New capability discovery for Dhan using Capabilities protocol."""

from __future__ import annotations

from typing import Any

from inc_trade.domain.constants.capabilities import (
    FEATURE_ALERTS,
    FEATURE_AUTH,
    FEATURE_DEPTH200,
    FEATURE_EXIT_ALL,
    FEATURE_FOREVER_ORDERS,
    FEATURE_HISTORICAL,
    FEATURE_INSTRUMENTS,
    FEATURE_IP_MANAGEMENT,
    FEATURE_MARGIN_CALCULATOR,
    FEATURE_MARKET_DATA,
    FEATURE_MTF,
    FEATURE_OPTION_CHAIN,
    FEATURE_OPTIONS,
    FEATURE_ORDERS,
    FEATURE_PORTFOLIO,
    FEATURE_SLICE_ORDERS,
    FEATURE_STREAMING,
    FEATURE_SUPER_ORDERS,
)
from inc_trade.ports.capabilities import Capabilities


class DhanCapabilities(Capabilities):
    """Dhan broker capability discovery implementation."""

    def has_feature(self, feature: str) -> bool:
        """Check if Dhan supports a specific feature."""
        return feature in {
            # Core features
            FEATURE_ORDERS,
            FEATURE_MARKET_DATA,
            FEATURE_PORTFOLIO,
            FEATURE_HISTORICAL,
            FEATURE_INSTRUMENTS,
            FEATURE_AUTH,
            FEATURE_STREAMING,
            # Dhan-specific features
            FEATURE_SUPER_ORDERS,
            FEATURE_FOREVER_ORDERS,
            FEATURE_MARGIN_CALCULATOR,
            FEATURE_SLICE_ORDERS,
            FEATURE_DEPTH200,
            FEATURE_OPTION_CHAIN,
            FEATURE_OPTIONS,
            FEATURE_MTF,
            FEATURE_EXIT_ALL,
            FEATURE_IP_MANAGEMENT,
            FEATURE_ALERTS,
            # Not supported (for completeness)
            # FEATURE_GTT,
            # FEATURE_BASKET_ORDERS,
            # FEATURE_EDIS,
            # FEATURE_NEWS,
        }

    def get_feature_metadata(self, feature: str) -> dict[str, Any]:
        """Get metadata about a Dhan feature."""
        metadata = {
            FEATURE_ORDERS: {
                "description": "Place, modify, cancel orders",
                "supported_exchanges": ["NSE", "BSE", "NFO", "MCX"],
                "limitations": [],
            },
            FEATURE_MARKET_DATA: {
                "description": "LTP, quote, depth for equities, F&O, commodities",
                "supported_exchanges": ["NSE", "BSE", "NFO", "MCX"],
                "limitations": [],
            },
            FEATURE_PORTFOLIO: {
                "description": "Positions, holdings, funds, trades",
                "supported_exchanges": ["NSE", "BSE", "NFO", "MCX"],
                "limitations": [],
            },
            FEATURE_HISTORICAL: {
                "description": "Daily and intraday candles with OHLCV",
                "supported_exchanges": ["NSE", "BSE", "NFO", "MCX"],
                "limitations": ["Max 3650 days for intraday"],
            },
            FEATURE_INSTRUMENTS: {
                "description": "Instrument master with search and resolution",
                "supported_exchanges": ["NSE", "BSE", "NFO", "MCX"],
                "limitations": [],
            },
            FEATURE_AUTH: {
                "description": "TOTP-based authentication with token persistence",
                "supported_exchanges": ["Dhan"],
                "limitations": [],
            },
            FEATURE_STREAMING: {
                "description": "WebSocket market data and order streams",
                "supported_exchanges": ["NSE", "BSE", "NFO", "MCX"],
                "limitations": ["Max 1000 instruments per connection"],
            },
            FEATURE_SUPER_ORDERS: {
                "description": "Super orders with target and stop-loss legs",
                "supported_exchanges": ["NSE", "BSE", "NFO"],
                "limitations": [],
            },
            FEATURE_FOREVER_ORDERS: {
                "description": "Forever orders (GTT-like) with OCO support",
                "supported_exchanges": ["NSE", "BSE", "NFO"],
                "limitations": [],
            },
            FEATURE_MARGIN_CALCULATOR: {
                "description": "Pre-trade margin calculation",
                "supported_exchanges": ["NSE", "BSE", "NFO", "MCX"],
                "limitations": [],
            },
            FEATURE_SLICE_ORDERS: {
                "description": "Broker-managed quantity splitting",
                "supported_exchanges": ["NSE", "BSE", "NFO"],
                "limitations": [],
            },
            FEATURE_DEPTH200: {
                "description": "Full order book depth (200 levels)",
                "supported_exchanges": ["NSE", "BSE", "NFO"],
                "limitations": [],
            },
            FEATURE_OPTION_CHAIN: {
                "description": "Option chain with greeks",
                "supported_exchanges": ["NFO"],
                "limitations": [],
            },
            FEATURE_OPTIONS: {
                "description": "Options trading support",
                "supported_exchanges": ["NFO"],
                "limitations": [],
            },
            FEATURE_MTF: {
                "description": "Margin Trading Facility",
                "supported_exchanges": ["NSE", "BSE"],
                "limitations": [],
            },
            FEATURE_EXIT_ALL: {
                "description": "Panic button to close all positions",
                "supported_exchanges": ["NSE", "BSE", "NFO", "MCX"],
                "limitations": [],
            },
            FEATURE_IP_MANAGEMENT: {
                "description": "Dynamic IP whitelisting",
                "supported_exchanges": ["Dhan"],
                "limitations": [],
            },
            FEATURE_ALERTS: {
                "description": "Price alerts and notifications",
                "supported_exchanges": ["NSE", "BSE", "NFO", "MCX"],
                "limitations": [],
            },
        }
        return metadata.get(
            feature,
            {
                "description": "Unknown feature",
                "supported_exchanges": [],
                "limitations": ["Not supported by Dhan"],
            },
        )


def dhan_capabilities() -> Capabilities:
    """Factory function for Dhan capabilities."""
    return DhanCapabilities()
