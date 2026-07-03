"""Upstox instruments — complete.json.gz loader, search, and resolve."""

from __future__ import annotations

import logging
import threading
from collections import defaultdict
from pathlib import Path

from brokers.adapters.upstox.config import EXCHANGE_TO_SEGMENT
from brokers.adapters.upstox.instrument_definition import UpstoxInstrumentDefinition
from brokers.adapters.upstox.instrument_loader import UpstoxInstrumentLoader
from brokers.config.indices import index_upstox_key, upstox_index_segment
from brokers.ports.instruments import InstrumentInfo

logger = logging.getLogger(__name__)


def fallback_upstox_instrument_key(symbol: str, exchange: str = "NSE") -> str:
    idx = index_upstox_key(symbol)
    if idx:
        return idx
    segment = upstox_index_segment(symbol) or EXCHANGE_TO_SEGMENT.get(
        exchange.upper(), exchange
    )
    return f"{segment}|{symbol}"


def resolve_upstox_instrument_key(
    symbol: str,
    exchange: str = "NSE",
    instruments: "UpstoxInstruments | None" = None,
) -> str:
    if instruments is not None and instruments.is_loaded:
        return instruments.instrument_key(symbol, exchange)
    return fallback_upstox_instrument_key(symbol, exchange)


class UpstoxInstruments:
    def __init__(self, cache_path: Path | None = None) -> None:
        self._cache_path = cache_path or Path(".cache/upstox/complete.json.gz")
        self._loader = UpstoxInstrumentLoader()
        self._by_key: dict[str, UpstoxInstrumentDefinition] = {}
        self._by_symbol_segment: dict[tuple[str, str], UpstoxInstrumentDefinition] = {}
        self._expiries_by_underlying: dict[str, set[str]] = defaultdict(set)
        self._lock = threading.RLock()
        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def load(self, source: str | None = None, segment: str | None = None) -> None:
        del segment  # protocol compat — full catalog always loaded
        path = Path(source) if source else self._cache_path
        if not path.exists():
            path = self._loader.download(path)
        defs = self._loader.load(path)
        with self._lock:
            self._by_key.clear()
            self._by_symbol_segment.clear()
            self._expiries_by_underlying.clear()
            for d in defs:
                if d.instrument_key:
                    self._by_key[d.instrument_key] = d
                sym = (d.symbol or d.trading_symbol).upper()
                if sym and d.exchange_segment:
                    self._by_symbol_segment[(sym, d.exchange_segment.upper())] = d
                if d.expiry:
                    underlying = (d.underlying_symbol or d.symbol or "").upper()
                    if underlying:
                        exp = d.expiry
                        if isinstance(exp, (int, float)):
                            from datetime import datetime, timezone

                            try:
                                exp = datetime.fromtimestamp(
                                    exp / 1000, tz=timezone.utc
                                ).strftime("%Y-%m-%d")
                            except (ValueError, OSError):
                                continue
                        self._expiries_by_underlying[underlying].add(str(exp))
            self._loaded = True
        logger.info("upstox_instruments_loaded", extra={"count": len(defs)})

    def search(self, query: str, limit: int = 10) -> list[InstrumentInfo]:
        query_upper = query.upper()
        results: list[InstrumentInfo] = []
        with self._lock:
            for d in self._by_key.values():
                sym = (d.symbol or d.trading_symbol).upper()
                if query_upper in sym or query_upper in d.name.upper():
                    results.append(self._to_info(d))
                    if len(results) >= limit:
                        break
        return results

    def _resolve_definition(
        self, symbol: str, exchange: str = "NSE"
    ) -> UpstoxInstrumentDefinition | None:
        idx_key = index_upstox_key(symbol)
        if idx_key:
            with self._lock:
                return self._by_key.get(idx_key)

        segment = upstox_index_segment(symbol) or f"{exchange.upper()}_EQ"
        with self._lock:
            d = self._by_symbol_segment.get((symbol.upper(), segment.upper()))
            if d is None:
                d = self._by_symbol_segment.get((symbol.upper(), exchange.upper()))
            return d

    def resolve(self, symbol: str, exchange: str = "NSE") -> InstrumentInfo | None:
        d = self._resolve_definition(symbol, exchange)
        return self._to_info(d) if d else None

    def instrument_key(self, symbol: str, exchange: str = "NSE") -> str:
        d = self._resolve_definition(symbol, exchange)
        if d and d.instrument_key:
            return d.instrument_key
        return fallback_upstox_instrument_key(symbol, exchange)

    def list_option_expiries(self, underlying: str) -> list[str]:
        with self._lock:
            expiries = self._expiries_by_underlying.get(underlying.upper(), set())
            return sorted(expiries)

    @staticmethod
    def _to_info(d: UpstoxInstrumentDefinition) -> InstrumentInfo:
        return InstrumentInfo(
            symbol=d.symbol or d.trading_symbol,
            exchange=d.exchange,
            segment=d.exchange_segment,
            name=d.name,
            lot_size=d.lot_size,
        )
