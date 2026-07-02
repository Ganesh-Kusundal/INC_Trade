"""Instrument service — application-level symbol resolution.

Adds auto-loading, fuzzy search, and exchange-aware resolution on
top of the raw InstrumentPort.
"""

from __future__ import annotations

import logging
import threading

from brokers.ports.instruments import InstrumentInfo, InstrumentPort

logger = logging.getLogger(__name__)


class InstrumentService:
    def __init__(self, instruments: InstrumentPort, auto_load: bool = True):
        self._instruments = instruments
        self._loaded = False
        self._lock = threading.Lock()
        if auto_load:
            self._ensure_loaded()

    def search(self, query: str, limit: int = 10) -> list[InstrumentInfo]:
        self._ensure_loaded()
        return self._instruments.search(query, limit)

    def resolve(self, symbol: str, exchange: str = "NSE") -> InstrumentInfo | None:
        self._ensure_loaded()
        return self._instruments.resolve(symbol, exchange)

    def reload(self) -> None:
        with self._lock:
            self._instruments.load()
            self._loaded = True
            logger.info("instruments_reloaded")

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if not self._loaded:
                self._instruments.load()
                self._loaded = True
