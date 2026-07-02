"""In-memory instrument resolver.

Mirrors Trade_J ``UpstoxInstrumentResolver``: index by instrument_key, by
(symbol, exchange_segment), and prefix search.
"""

from __future__ import annotations

import logging
import threading
from collections import defaultdict
from collections.abc import Iterable

from domain.symbols import normalize_exchange, normalize_symbol

from brokers.common.date_utils import format_expiry_components
from brokers.common.instrument_resolver import generate_alternate_symbol_keys

from .definition import UpstoxInstrumentDefinition

logger = logging.getLogger(__name__)


def _generate_alternate_keys(
    symbol: str,
    inst_type: str,
    expiry: str | None = None,
    strike: float | None = None,
    option_type: str | None = None,
    underlying: str | None = None,
    canonical_symbol: str | None = None,
) -> list[str]:
    """Generate alternate lookup keys for an instrument definition."""
    return generate_alternate_symbol_keys(
        symbol=symbol,
        inst_type=inst_type,
        expiry=expiry,
        strike=strike,
        option_type=option_type,
        underlying=underlying,
        canonical_symbol=canonical_symbol,
    )


class UpstoxInstrumentResolver:
    """In-memory index of ``UpstoxInstrumentDefinition`` records."""

    def __init__(self) -> None:
        self._by_key: dict[str, UpstoxInstrumentDefinition] = {}
        self._by_symbol_segment: dict[tuple[str, str], UpstoxInstrumentDefinition] = {}
        self._by_symbol_index: dict[str, list[UpstoxInstrumentDefinition]] = defaultdict(list)
        # Underlying symbol -> set of unique expiry dates (for option/future chains).
        # The upstream /v2/option/expiry endpoint is DEPRECATED, so we derive
        # expiries from the in-memory instrument master instead.
        self._expiries_by_underlying: dict[str, set[str]] = defaultdict(set)
        self._future_expiries_by_underlying: dict[str, set[str]] = defaultdict(set)
        self._lock = threading.RLock()
        self._loaded = False

    def is_loaded(self) -> bool:
        with self._lock:
            return self._loaded

    def reset(self) -> None:
        with self._lock:
            self._by_key.clear()
            self._by_symbol_segment.clear()
            self._by_symbol_index.clear()
            self._expiries_by_underlying.clear()
            self._future_expiries_by_underlying.clear()
            self._loaded = False

    def register(self, definition: UpstoxInstrumentDefinition) -> None:
        with self._lock:
            if definition.instrument_key:
                self._by_key[definition.instrument_key] = definition
            sym = definition.symbol or definition.trading_symbol
            if sym and definition.exchange_segment:
                # Primary index
                key = (sym.upper(), definition.exchange_segment.upper())
                self._by_symbol_segment[key] = definition

                # Retrieve canonical segments/exchanges for alias indexing
                from brokers.common.instruments import InstrumentRegistry
                from brokers.upstox.instruments.segment_mapper import UpstoxSegmentMapper

                xv2_segment = UpstoxSegmentMapper.to_safe(definition.exchange_segment)
                canonical_exch = InstrumentRegistry.canonical_exchange(xv2_segment)

                # Generate alternate lookup keys
                alt_keys = generate_alternate_symbol_keys(
                    symbol=sym,
                    inst_type=str(definition.instrument_type),
                    expiry=definition.expiry,
                    strike=definition.strike,
                    option_type=definition.option_type,
                    underlying=definition.underlying_symbol,
                    canonical_symbol=definition.name,
                )

                for k in alt_keys:
                    self._by_symbol_segment[(k, definition.exchange_segment.upper())] = definition
                    self._by_symbol_segment[(k, xv2_segment.value.upper())] = definition
                    self._by_symbol_segment[(k, canonical_exch.upper())] = definition

                if sym:
                    self._by_symbol_index[sym.upper()].append(definition)

                # Index option/future expiries by underlying symbol so the
                # options adapter can derive expiries without calling the
                # deprecated /v2/option/expiry endpoint.
                if definition.is_option and definition.expiry and definition.underlying_symbol:
                    self._expiries_by_underlying[normalize_symbol(definition.underlying_symbol)].add(
                        definition.expiry[:10]
                    )
                if definition.is_future and definition.expiry and definition.underlying_symbol:
                    self._future_expiries_by_underlying[
                        normalize_symbol(definition.underlying_symbol)
                    ].add(definition.expiry[:10])
            self._loaded = True

    def register_many(self, definitions: Iterable[UpstoxInstrumentDefinition]) -> None:
        for d in definitions:
            self.register(d)

    def resolve(
        self,
        instrument_key: str | None = None,
        *,
        symbol: str | None = None,
        exchange_segment: str | None = None,
    ) -> UpstoxInstrumentDefinition | None:
        with self._lock:
            if instrument_key:
                d = self._by_key.get(instrument_key)
                if d is not None:
                    return d
            if symbol and exchange_segment:
                clean_sym = normalize_symbol(symbol)
                clean_seg = normalize_exchange(exchange_segment)

                # 1. Try standard lookup
                d = self._by_symbol_segment.get((clean_sym, clean_seg))
                if d is not None:
                    return d

                # 2. Try stripped lookup
                stripped_sym = clean_sym.replace(" ", "").replace("-", "").replace("_", "")
                d = self._by_symbol_segment.get((stripped_sym, clean_seg))
                if d is not None:
                    return d

                # 3. Try standardizing Option format CALL -> CE, PUT -> PE
                if clean_sym.endswith("CALL"):
                    clean_sym = clean_sym[:-4] + "CE"
                elif clean_sym.endswith("PUT"):
                    clean_sym = clean_sym[:-3] + "PE"

                d = self._by_symbol_segment.get((clean_sym, clean_seg))
                if d is not None:
                    return d

                # 4. Try stripped Option format standard
                stripped_cepe = clean_sym.replace(" ", "").replace("-", "").replace("_", "")
                d = self._by_symbol_segment.get((stripped_cepe, clean_seg))
                if d is not None:
                    return d
        return None

    def require(
        self,
        instrument_key: str | None = None,
        *,
        symbol: str | None = None,
        exchange_segment: str | None = None,
    ) -> UpstoxInstrumentDefinition:
        d = self.resolve(
            instrument_key=instrument_key, symbol=symbol, exchange_segment=exchange_segment
        )
        if d is None:
            ident = instrument_key or f"{symbol}@{exchange_segment}"
            raise ValueError(f"Upstox instrument not found: {ident}")
        return d

    def search(
        self, prefix: str, exchange_segment: str | None = None, limit: int = 50
    ) -> list[UpstoxInstrumentDefinition]:
        if not prefix:
            return []
        needle = prefix.upper()
        with self._lock:
            results: list[UpstoxInstrumentDefinition] = []
            for sym, defs in self._by_symbol_index.items():
                if not sym.startswith(needle):
                    continue
                for d in defs:
                    if exchange_segment and d.exchange_segment.upper() != exchange_segment.upper():
                        continue
                    results.append(d)
                    if len(results) >= limit:
                        return results
        return results

    def keys(self) -> list[str]:
        with self._lock:
            return list(self._by_key.keys())

    def list_option_expiries(self, underlying: str) -> list[str]:
        """Return sorted, future-dated option expiry strings for *underlying*.

        Derives expiries from the loaded instrument master instead of calling
        the deprecated ``/v2/option/expiry`` endpoint. Returns ``[]`` only if
        no matching options are loaded; callers that need to distinguish
        "not loaded" from "no expiries" should check :meth:`is_loaded`.
        """
        from datetime import date

        with self._lock:
            if not self._loaded:
                raise RuntimeError("Upstox instruments not loaded; cannot derive option expiries")
            exps = self._expiries_by_underlying.get(normalize_symbol(underlying), set())
            today = date.today().isoformat()
            return sorted(e for e in exps if e >= today)

    def list_future_expiries(self, underlying: str) -> list[str]:
        """Return sorted, future-dated futures expiry strings for *underlying*."""
        from datetime import date

        with self._lock:
            if not self._loaded:
                raise RuntimeError("Upstox instruments not loaded; cannot derive future expiries")
            exps = self._future_expiries_by_underlying.get(normalize_symbol(underlying), set())
            today = date.today().isoformat()
            return sorted(e for e in exps if e >= today)

    def list_future_contracts(self, underlying: str) -> list[UpstoxInstrumentDefinition]:
        """Return active future instrument definitions for *underlying*."""
        from datetime import date

        und = normalize_symbol(underlying)
        today = date.today().isoformat()
        with self._lock:
            if not self._loaded:
                raise RuntimeError("Upstox instruments not loaded; cannot list future contracts")
            contracts: list[UpstoxInstrumentDefinition] = []
            for defs in self._by_symbol_index.values():
                for d in defs:
                    if not d.is_future:
                        continue
                    if (d.underlying_symbol or "").strip().upper() != und:
                        continue
                    if d.expiry and d.expiry[:10] < today:
                        continue
                    contracts.append(d)
            return sorted(contracts, key=lambda c: (c.expiry or "", c.trading_symbol or ""))

    def __len__(self) -> int:
        with self._lock:
            return len(self._by_key)


