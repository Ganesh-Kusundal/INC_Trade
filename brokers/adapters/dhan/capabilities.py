"""Dhan capabilities definition."""

from dataclasses import dataclass


@dataclass
class DhanCapabilities:
    """Defines supported features for the Dhan broker adapter."""

    supports_mtf: bool = True
    supports_gtt: bool = True
    supports_bracket_orders: bool = True
    supports_cover_orders: bool = True
    supports_amo: bool = True
    supports_historical_data: bool = True
    supports_websocket_quotes: bool = True
    supports_websocket_order_updates: bool = True
    supports_options_trading: bool = True
