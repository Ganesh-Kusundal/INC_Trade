"""Dhan Symbol Validator adapter."""

from __future__ import annotations

import logging

from brokers.adapters.dhan.identity import DhanInstrumentResolver

logger = logging.getLogger(__name__)


class DhanSymbolValidator:
    """Symbol validation adapter to prevent bad orders from firing."""

    def __init__(self, resolver: DhanInstrumentResolver) -> None:
        self._resolver = resolver

    def validate_symbol(self, symbol: str, exchange: str) -> bool:
        """Check if symbol exists in the master list."""
        try:
            self._resolver.resolve(symbol, exchange)
            return True
        except Exception:
            logger.warning(f"invalid_symbol_detected: {symbol} on {exchange}")
            return False
