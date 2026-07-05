"""Centralized symbol normalization utilities."""

from __future__ import annotations


def normalize_symbol(symbol: str) -> str:
    """Normalize a trading symbol to canonical uppercase-stripped form."""
    return symbol.strip().upper()


def normalize_exchange(exchange: str) -> str:
    """Normalize an exchange identifier to canonical uppercase form."""
    return exchange.strip().upper()


def make_position_key(symbol: str, exchange: str) -> str:
    """Create a canonical position lookup key from symbol and exchange."""
    return f"{normalize_symbol(symbol)}:{normalize_exchange(exchange)}"


def make_instrument_key(symbol: str, exchange: str) -> tuple[str, str]:
    """Create a normalized (symbol, exchange) tuple for instrument lookups."""
    return (normalize_symbol(symbol), normalize_exchange(exchange))
