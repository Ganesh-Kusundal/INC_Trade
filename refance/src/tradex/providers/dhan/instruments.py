"""Dhan instrument mapper — downloads and caches the Dhan security master."""

from __future__ import annotations

import asyncio
from typing import Optional

import httpx
from tradex.core.cache import TTLCache
from tradex.core.logging_config import get_logger
from tradex.domain.enums import Exchange, InstrumentType
from tradex.domain.mapping import SecurityMapping
from tradex.providers.dhan.mapping import DhanMapper

logger = get_logger("providers.dhan.instruments")


class DhanInstrumentMapper:
    """Dhan-specific instrument mapper that downloads the security master."""

    SECURITY_MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master.csv"

    def __init__(self, cache_ttl: int = 3600) -> None:
        self._mapper = DhanMapper("dhan", cache_ttl)
        self._cache = TTLCache[str, SecurityMapping](max_size=50000, default_ttl=float(cache_ttl))
        self._loaded = False
        self._loading = False
        self._lock = asyncio.Lock()

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def count(self) -> int:
        return self._mapper.count

    async def load_from_provider(self) -> None:
        """Download and load the Dhan security master CSV."""
        async with self._lock:
            if self._loaded or self._loading:
                return
            self._loading = True

        try:
            logger.info("dhan_instruments_loading")

            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.get(self.SECURITY_MASTER_URL)
                response.raise_for_status()

            # Parse CSV
            lines = response.text.strip().split("\n")
            if len(lines) < 2:
                logger.warning("dhan_instruments_empty")
                return

            headers = lines[0].split(",")
            rows = []
            for line in lines[1:]:
                values = line.split(",")
                if len(values) == len(headers):
                    row = dict(zip(headers, values))
                    rows.append(row)

            await self._mapper.load(rows)
            self._loaded = True

            logger.info("dhan_instruments_loaded", count=len(rows))

        except Exception as e:
            logger.error("dhan_instruments_load_failed", error=str(e))
        finally:
            self._loading = False

    async def resolve_symbol(
        self, symbol: str, exchange: Exchange = Exchange.NSE
    ) -> Optional[SecurityMapping]:
        """Resolve a trading symbol to Dhan security ID."""
        if not self._loaded:
            await self.load_from_provider()
        return await self._mapper.resolve_by_symbol(symbol, exchange)

    async def resolve_security_id(self, broker_id: str) -> Optional[SecurityMapping]:
        """Resolve a Dhan security ID to canonical info."""
        if not self._loaded:
            await self.load_from_provider()
        return await self._mapper.resolve_by_broker_id(broker_id)

    async def search(
        self,
        symbol: str,
        exchange: Exchange = Exchange.NSE,
        instrument_type: Optional[InstrumentType] = None,
    ) -> list[SecurityMapping]:
        """Search for instruments matching criteria."""
        if not self._loaded:
            await self.load_from_provider()

        results = []
        for mapping in self._mapper._mappings.values():
            if mapping.canonical_symbol.upper() == symbol.upper():
                if exchange != Exchange.UNKNOWN and mapping.canonical_exchange != exchange:
                    continue
                if instrument_type and mapping.instrument_type != instrument_type:
                    continue
                results.append(mapping)
        return results
