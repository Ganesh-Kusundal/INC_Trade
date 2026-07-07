"""Shared instrument registry — manages resolvers across brokers.

Provides a unified resolution interface that delegates to broker-specific
resolvers based on the broker_id or exchange.

Usage::

    from brokers.common.instrument_registry import SharedInstrumentRegistry

    registry = SharedInstrumentRegistry()
    registry.register_resolver("dhan", dhan_resolver)
    registry.register_resolver("upstox", upstox_resolver)

    # Resolve across all brokers
    instrument = registry.resolve("RELIANCE", Exchange.NSE)

    # Resolve for a specific broker
    instrument = registry.resolve_for("RELIANCE", Exchange.NSE, broker_id="dhan")
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

from brokers.domain.enums import Exchange
from brokers.common.instrument_resolver import (
    InstrumentNotFoundError,
    InstrumentResolver,
    ResolvedInstrument,
)


@dataclass(frozen=True)
class ResolvedInstrumentInfo:
    """Aggregated resolution result across all brokers."""

    symbol: str
    exchange: Exchange
    results: dict[str, ResolvedInstrument] = field(default_factory=dict)

    def for_broker(self, broker_id: str) -> ResolvedInstrument | None:
        """Get the resolution result for a specific broker."""
        return self.results.get(broker_id)

    @property
    def primary(self) -> ResolvedInstrument | None:
        """Get the first resolution result (arbitrary broker order)."""
        if not self.results:
            return None
        return next(iter(self.results.values()))

    @property
    def broker_count(self) -> int:
        """Number of brokers that resolved this instrument."""
        return len(self.results)


class SharedInstrumentRegistry:
    """Manages instrument resolvers across all brokers.

    Provides unified resolution that delegates to broker-specific resolvers.
    Thread-safe via a single lock.

    Usage::

        registry = SharedInstrumentRegistry()
        registry.register_resolver("dhan", dhan_resolver)
        registry.register_resolver("upstox", upstox_resolver)

        # Unified resolution
        result = registry.resolve("RELIANCE", Exchange.NSE)
        dhan_id = result.for_broker("dhan").broker_id
        upstox_key = result.for_broker("upstox").broker_id
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._resolvers: dict[str, InstrumentResolver] = {}
        self._default_broker: str | None = None

    def register_resolver(self, broker_id: str, resolver: InstrumentResolver) -> None:
        """Register a broker-specific instrument resolver."""
        with self._lock:
            self._resolvers[broker_id] = resolver

    def unregister_resolver(self, broker_id: str) -> bool:
        """Remove a broker's resolver. Returns True if removed."""
        with self._lock:
            if broker_id in self._resolvers:
                del self._resolvers[broker_id]
                if self._default_broker == broker_id:
                    self._default_broker = None
                return True
            return False

    def set_default_broker(self, broker_id: str) -> None:
        """Set the default broker for unified resolution."""
        with self._lock:
            if broker_id not in self._resolvers:
                raise ValueError(f"Broker {broker_id!r} not registered")
            self._default_broker = broker_id

    @property
    def registered_brokers(self) -> list[str]:
        """Return list of registered broker IDs."""
        with self._lock:
            return list(self._resolvers.keys())

    def resolve(self, symbol: str, exchange: Exchange) -> ResolvedInstrumentInfo:
        """Resolve a symbol across all registered brokers.

        Returns a ResolvedInstrumentInfo with results from each broker
        that could resolve the instrument.
        """
        results: dict[str, ResolvedInstrument] = {}
        with self._lock:
            for broker_id, resolver in self._resolvers.items():
                try:
                    inst = resolver.resolve(symbol, exchange)
                    results[broker_id] = inst
                except InstrumentNotFoundError:
                    continue
        if not results:
            raise InstrumentNotFoundError(symbol, exchange.value)
        return ResolvedInstrumentInfo(
            symbol=symbol,
            exchange=exchange,
            results=results,
        )

    def resolve_for(
        self, symbol: str, exchange: Exchange, broker_id: str
    ) -> ResolvedInstrument:
        """Resolve a symbol for a specific broker.

        Raises InstrumentNotFoundError if the broker is not registered
        or the symbol is not found.
        """
        with self._lock:
            resolver = self._resolvers.get(broker_id)
        if resolver is None:
            raise InstrumentNotFoundError(
                symbol, exchange.value, f"broker {broker_id!r} not registered"
            )
        return resolver.resolve(symbol, exchange)

    def search(self, query: str, limit: int = 20) -> list[ResolvedInstrumentInfo]:
        """Search across all brokers and return aggregated results."""
        # Collect unique symbols from all resolvers
        seen: set[str] = set()
        infos: list[ResolvedInstrumentInfo] = []
        with self._lock:
            for broker_id, resolver in self._resolvers.items():
                for inst in resolver.search(query, limit=limit):
                    key = f"{inst.symbol}:{inst.exchange.value}"
                    if key not in seen:
                        seen.add(key)
                        infos.append(
                            ResolvedInstrumentInfo(
                                symbol=inst.symbol,
                                exchange=inst.exchange,
                                results={broker_id: inst},
                            )
                        )
                    else:
                        # Add this broker's result to existing info
                        for info in infos:
                            if (
                                info.symbol == inst.symbol
                                and info.exchange == inst.exchange
                            ):
                                info.results[broker_id] = inst
                                break
        return infos[:limit]

    def stats(self) -> dict[str, dict[str, int]]:
        """Return stats from each registered resolver."""
        with self._lock:
            return {
                broker_id: resolver.stats()
                for broker_id, resolver in self._resolvers.items()
            }

    def total_instruments(self) -> int:
        """Total instrument count across all brokers."""
        with self._lock:
            return sum(resolver.stats().get("total", 0) for resolver in self._resolvers.values())


__all__ = [
    "ResolvedInstrumentInfo",
    "SharedInstrumentRegistry",
]
