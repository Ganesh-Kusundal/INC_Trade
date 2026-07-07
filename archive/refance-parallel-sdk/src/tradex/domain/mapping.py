"""Security ID mapping — abstracts broker-specific identifiers.

Users work with canonical instruments. This module handles the
bidirectional mapping between canonical IDs and broker-specific IDs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from tradex.core.cache import TTLCache
from tradex.domain.enums import Exchange, InstrumentType


@dataclass
class SecurityMapping:
    """A single mapping entry between canonical and broker-specific IDs."""

    canonical_symbol: str
    canonical_exchange: Exchange
    broker_security_id: str
    broker_symbol: str = ""
    broker_exchange: str = ""
    instrument_type: InstrumentType = InstrumentType.EQUITY
    lot_size: int = 1
    tick_size: float = 0.05
    isin: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


class InstrumentMapper:
    """Manages security ID mappings for a single broker.

    Downloads and caches the broker's security master.
    Provides bidirectional lookup between canonical symbols
    and broker-specific security IDs.
    """

    def __init__(self, broker_name: str, cache_ttl: int = 3600) -> None:
        self._broker = broker_name
        self._cache = TTLCache[str, SecurityMapping](max_size=50000, default_ttl=float(cache_ttl))
        self._reverse_cache = TTLCache[str, SecurityMapping](
            max_size=50000, default_ttl=float(cache_ttl)
        )
        self._loaded = False
        self._mappings: dict[str, SecurityMapping] = {}

    @property
    def broker(self) -> str:
        return self._broker

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    async def load(self, rows: list[dict[str, Any]]) -> None:
        """Load mappings from security master data."""
        for row in rows:
            mapping = self._parse_row(row)
            if mapping:
                key = f"{mapping.canonical_symbol}:{mapping.canonical_exchange.value}"
                broker_key = f"{mapping.broker_security_id}:{self._broker}"
                self._mappings[broker_key] = mapping
                await self._cache.put(key, mapping)
                await self._reverse_cache.put(broker_key, mapping)
        self._loaded = True

    async def resolve_by_symbol(
        self, symbol: str, exchange: Exchange = Exchange.NSE
    ) -> Optional[SecurityMapping]:
        """Resolve canonical symbol to broker-specific ID."""
        key = f"{symbol}:{exchange.value}"
        return await self._cache.get(key)

    async def resolve_by_broker_id(self, broker_id: str) -> Optional[SecurityMapping]:
        """Resolve broker-specific security ID to canonical."""
        key = f"{broker_id}:{self._broker}"
        return await self._reverse_cache.get(key)

    def _parse_row(self, row: dict[str, Any]) -> Optional[SecurityMapping]:
        """Parse a security master row into a mapping."""
        # Override in provider-specific subclasses
        return None

    @property
    def count(self) -> int:
        return len(self._mappings)

    async def refresh(self, rows: list[dict[str, Any]]) -> None:
        """Refresh all mappings."""
        await self._cache.clear()
        await self._reverse_cache.clear()
        self._mappings.clear()
        self._loaded = False
        await self.load(rows)

    async def search(self, symbol: str, exchange: Exchange = Exchange.NSE) -> list[SecurityMapping]:
        """Search for mappings matching a symbol pattern.

        Returns all mappings whose canonical_symbol contains the
        search string (case-insensitive) for the given exchange.

        Args:
            symbol: Partial or full symbol to search for.
            exchange: Exchange to search in.

        Returns:
            List of matching SecurityMapping objects.
        """
        results = []
        symbol_upper = symbol.upper()
        for key, mapping in self._mappings.items():
            if (
                symbol_upper in mapping.canonical_symbol.upper()
                and mapping.canonical_exchange == exchange
            ):
                results.append(mapping)
        return results
