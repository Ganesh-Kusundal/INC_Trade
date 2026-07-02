"""Centralized symbol normalization utilities — single source of truth.

Previously, symbol normalization was scattered across 128+ call sites
with ``symbol.upper().strip()`` patterns. This module provides a canonical
normalization function that all callers should use.

Usage::

    from domain.symbols import normalize_symbol, normalize_exchange, make_position_key

    sym = normalize_symbol("  Reliance  ")  # "RELIANCE"
    exch = normalize_exchange("nse")         # "NSE"
    key = make_position_key("RELIANCE", "NSE")  # "RELIANCE:NSE"
"""

from __future__ import annotations


def normalize_symbol(symbol: str) -> str:
    """Normalize a trading symbol to canonical uppercase-stripped form.

    This is the SINGLE canonical function for symbol normalization.
    All callers should use this instead of inline ``.upper().strip()``.

    Parameters
    ----------
    symbol : str
        Raw symbol string (e.g., "  Reliance  ", "reliance", "RELIANCE").

    Returns
    -------
    str
        Normalized symbol (e.g., "RELIANCE").
    """
    return symbol.strip().upper()


def normalize_exchange(exchange: str) -> str:
    """Normalize an exchange identifier to canonical uppercase form.

    Parameters
    ----------
    exchange : str
        Raw exchange string (e.g., "nse", "NSE", "nfo").

    Returns
    -------
    str
        Normalized exchange (e.g., "NSE", "NFO").
    """
    return exchange.strip().upper()


def make_position_key(symbol: str, exchange: str) -> str:
    """Create a canonical position lookup key from symbol and exchange.

    This is the SINGLE canonical key format used by PositionManager
    and other position-tracking code.

    Parameters
    ----------
    symbol : str
        Trading symbol.
    exchange : str
        Exchange identifier.

    Returns
    -------
    str
        Position key in "SYMBOL:EXCHANGE" format.
    """
    return f"{normalize_symbol(symbol)}:{normalize_exchange(exchange)}"


def make_instrument_key(symbol: str, exchange: str) -> tuple[str, str]:
    """Create a canonical (symbol, exchange) tuple for instrument lookups.

    Parameters
    ----------
    symbol : str
        Trading symbol.
    exchange : str
        Exchange identifier.

    Returns
    -------
    tuple[str, str]
        Normalized (symbol, exchange) pair.
    """
    return (normalize_symbol(symbol), normalize_exchange(exchange))
