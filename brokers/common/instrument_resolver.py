"""Common instrument resolver — shared interface for symbol-to-broker-ID resolution.

Every broker has its own instrument ID format:
  - Dhan: numeric security_id (e.g. "3456")
  - Upstox: composite instrument_key (e.g. "NSE_EQ|INE002A01018")

This module provides the common interface plus a thread-safe in-memory base.
Broker-specific resolvers extend this with their own loading and lookup logic.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable

from brokers.domain.enums import Exchange, InstrumentType


# ── Resolver result ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ResolvedInstrument:
    """Result of instrument resolution — carries broker-specific IDs.

    ``broker_id`` is the broker-native identifier:
      - Dhan: numeric security_id string
      - Upstox: instrument_key string

    ``segment`` is the broker-native exchange segment:
      - Dhan: "NSE_EQ", "NSE_FNO", etc.
      - Upstox: "NSE_EQ", "NSE_FO", etc.
    """

    symbol: str
    exchange: Exchange
    broker_id: str
    segment: str
    instrument_type: InstrumentType = InstrumentType.EQUITY
    lot_size: int = 1
    tick_size: Decimal = Decimal("0.05")
    trading_symbol: str = ""
    expiry: str | None = None
    strike: Decimal | None = None
    isin: str = ""
    underlying: str = ""


class InstrumentNotFoundError(Exception):
    """Raised when a symbol cannot be resolved to a broker instrument."""

    def __init__(self, symbol: str, exchange: str, broker: str = "") -> None:
        self.symbol = symbol
        self.exchange = exchange
        self.broker = broker
        super().__init__(
            f"Instrument not found: {symbol} on {exchange}"
            + (f" ({broker})" if broker else "")
        )


# ── Resolver protocol ──────────────────────────────────────────────────────


@runtime_checkable
class InstrumentResolver(Protocol):
    """Protocol for instrument resolution — every broker must implement this."""

    def resolve(self, symbol: str, exchange: Exchange) -> ResolvedInstrument:
        """Resolve a canonical symbol + exchange to a broker instrument.

        Raises InstrumentNotFoundError if the symbol is not in the registry.
        """
        ...

    def resolve_by_broker_id(self, broker_id: str) -> ResolvedInstrument:
        """Reverse lookup: broker ID → resolved instrument.

        Raises InstrumentNotFoundError if not found.
        """
        ...

    def search(self, query: str, limit: int = 20) -> list[ResolvedInstrument]:
        """Fuzzy search for instruments by symbol or trading symbol."""
        ...

    def register_many(self, instruments: list[ResolvedInstrument]) -> int:
        """Bulk-register instruments. Returns count successfully registered."""
        ...

    @property
    def is_loaded(self) -> bool:
        """Whether instrument master data has been loaded."""
        ...

    def stats(self) -> dict[str, Any]:
        """Return resolver statistics (total, by_type, etc.)."""
        ...


# ── In-memory base implementation ──────────────────────────────────────────


class InMemoryInstrumentResolver:
    """Thread-safe in-memory instrument registry.

    Broker-specific resolvers inherit from this and override
    ``_generate_alternate_keys`` to add broker-specific lookup variants.
    """

    def __init__(self, broker_name: str = "") -> None:
        self._broker_name = broker_name
        self._lock = threading.RLock()

        # Primary indexes
        self._by_symbol: dict[str, ResolvedInstrument] = {}
        self._by_broker_id: dict[str, ResolvedInstrument] = {}
        self._by_trading_symbol: dict[str, ResolvedInstrument] = {}

        # Alternate-key index (stripped, formatted variants)
        self._by_alternate: dict[str, ResolvedInstrument] = {}

        # Loaded flag
        self._loaded = False

    # ── Public API ───────────────────────────────────────────────────────

    def resolve(self, symbol: str, exchange: Exchange) -> ResolvedInstrument:
        """Resolve a canonical symbol to a broker instrument.

        Tries multiple lookup strategies:
        1. Direct symbol match
        2. Stripped symbol (no spaces/underscores/dashes)
        3. Alternate keys (option/future formatting variants)
        4. Index symbol fallback (NIFTY, BANKNIFTY, etc.)
        """
        with self._lock:
            result = self._find(symbol, exchange)
            if result is not None:
                return result
        raise InstrumentNotFoundError(symbol, exchange.value, self._broker_name)

    def resolve_by_broker_id(self, broker_id: str) -> ResolvedInstrument:
        with self._lock:
            # Direct broker_id lookup
            inst = self._by_broker_id.get(broker_id)
            if inst is not None:
                return inst
            # Also check alternate keys (ISIN, identifier portion, etc.)
            inst = self._by_alternate.get(broker_id)
            if inst is not None:
                return inst
        raise InstrumentNotFoundError(broker_id, "(by_broker_id)", self._broker_name)

    def search(self, query: str, limit: int = 20) -> list[ResolvedInstrument]:
        q = query.upper().strip()
        results: list[ResolvedInstrument] = []
        seen: set[str] = set()
        with self._lock:
            for key, inst in self._by_symbol.items():
                if q in key.upper():
                    if inst.broker_id not in seen:
                        results.append(inst)
                        seen.add(inst.broker_id)
                    if len(results) >= limit:
                        return results
            # Also search trading symbols
            for ts, inst in self._by_trading_symbol.items():
                if q in ts.upper() and inst.broker_id not in seen:
                    results.append(inst)
                    seen.add(inst.broker_id)
                    if len(results) >= limit:
                        return results
        return results

    def register_many(self, instruments: list[ResolvedInstrument]) -> int:
        count = 0
        with self._lock:
            for inst in instruments:
                if self._register_one(inst):
                    count += 1
            self._loaded = True
        return count

    def register_one(self, instrument: ResolvedInstrument) -> bool:
        with self._lock:
            result = self._register_one(instrument)
            self._loaded = True
            return result

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def stats(self) -> dict[str, Any]:
        with self._lock:
            by_type: dict[str, int] = {}
            for inst in self._by_broker_id.values():
                key = inst.instrument_type.value
                by_type[key] = by_type.get(key, 0) + 1
            return {
                "total": len(self._by_broker_id),
                "by_type": by_type,
                "alternate_keys": len(self._by_alternate),
            }

    # ── Internal ─────────────────────────────────────────────────────────

    def _register_one(self, inst: ResolvedInstrument) -> bool:
        """Register a single instrument. Returns True if registered."""
        if not inst.broker_id:
            return False

        # Primary index by broker_id (always overwrite)
        self._by_broker_id[inst.broker_id] = inst

        # Symbol index — prefer EQUITY/INDEX/FUTURES over OPTIONS to avoid
        # expired options overriding the underlying ticker
        existing = self._by_symbol.get(inst.symbol)
        if existing is None or self._should_overwrite(existing, inst):
            self._by_symbol[inst.symbol] = inst
        # Also index by symbol+exchange for multi-exchange disambiguation
        self._by_symbol[f"{inst.symbol}:{inst.exchange.value}"] = inst

        # Trading symbol index
        if inst.trading_symbol:
            self._by_trading_symbol[inst.trading_symbol] = inst

        # Alternate keys
        for alt_key in self._generate_alternate_keys(inst):
            if alt_key not in self._by_alternate:
                self._by_alternate[alt_key] = inst

        return True

    @staticmethod
    def _should_overwrite(existing: ResolvedInstrument, new: ResolvedInstrument) -> bool:
        """Prefer EQUITY/FUTURES over OPTIONS to avoid stale overrides."""
        priority = {
            InstrumentType.EQUITY: 3,
            InstrumentType.FUTURES: 2,
            InstrumentType.INDEX: 4,
            InstrumentType.OPTIONS: 1,
            InstrumentType.CURRENCY: 1,
        }
        return priority.get(new.instrument_type, 0) >= priority.get(existing.instrument_type, 0)

    def _find(self, symbol: str, exchange: Exchange) -> ResolvedInstrument | None:
        """Multi-strategy lookup — tries direct, stripped, alternate keys."""
        # 1. Symbol+exchange direct match (most specific)
        key = f"{symbol}:{exchange.value}"
        inst = self._by_symbol.get(key)
        if inst is not None:
            return inst
        # 2. Direct symbol match (less specific)
        inst = self._by_symbol.get(symbol)
        if inst is not None:
            return inst

        # 2. Stripped symbol (remove spaces, underscores, dashes)
        stripped = _strip_symbol(symbol)
        inst = self._by_symbol.get(stripped)
        if inst is not None:
            return inst

        # 3. Alternate keys
        inst = self._by_alternate.get(symbol)
        if inst is not None:
            return inst

        inst = self._by_alternate.get(stripped)
        if inst is not None:
            return inst

        # 4. Uppercase variants
        upper = symbol.upper()
        inst = self._by_symbol.get(upper)
        if inst is not None:
            return inst

        inst = self._by_alternate.get(upper)
        if inst is not None:
            return inst

        # 5. Standardize option suffix (CALL→CE, PUT→PE)
        standardized = _standardize_option_suffix(stripped)
        if standardized != stripped:
            inst = self._by_alternate.get(standardized)
            if inst is not None:
                return inst

        # 6. Trading symbol lookup
        inst = self._by_trading_symbol.get(symbol)
        if inst is not None:
            return inst

        inst = self._by_trading_symbol.get(stripped)
        if inst is not None:
            return inst

        return None

    def _generate_alternate_keys(self, inst: ResolvedInstrument) -> list[str]:
        """Generate alternate lookup keys for an instrument.

        Override in broker-specific subclasses to add broker-specific formats.
        """
        keys: list[str] = []
        sym = inst.symbol
        ts = inst.trading_symbol

        # Stripped variants
        stripped = _strip_symbol(sym)
        if stripped != sym:
            keys.append(stripped)
        if ts:
            stripped_ts = _strip_symbol(ts)
            keys.append(stripped_ts)
            if stripped_ts != ts:
                keys.append(ts)

        # Option/future formatting variants
        if inst.instrument_type == InstrumentType.OPTIONS and inst.expiry and inst.strike is not None:
            # e.g. "NIFTY26JUN15900CE"
            compact = _compact_option_symbol(inst.underlying or sym, inst.expiry, inst.strike, "CE" if "CE" in sym.upper() else "PE")
            keys.append(compact)
            # Also try with CALL/PUT
            call_put = compact.replace("CE", "CALL").replace("PE", "PUT")
            keys.append(call_put)

        if inst.instrument_type == InstrumentType.FUTURES and inst.expiry:
            compact = _compact_future_symbol(inst.underlying or sym, inst.expiry)
            keys.append(compact)

        return keys


# ── Helpers ────────────────────────────────────────────────────────────────


def _strip_symbol(symbol: str) -> str:
    """Remove spaces, underscores, dashes from a symbol."""
    return symbol.replace(" ", "").replace("_", "").replace("-", "").upper()


def _standardize_option_suffix(symbol: str) -> str:
    """Standardize CALL→CE, PUT→PE in a symbol string."""
    upper = symbol.upper()
    upper = upper.replace("CALL", "CE").replace("PUT", "PE")
    return upper


def _compact_option_symbol(underlying: str, expiry: str, strike: Decimal, option_type: str) -> str:
    """Build compact option symbol like 'NIFTY26JUN15900CE'."""
    # Parse expiry "2026-06-26" → "26JUN"
    parts = expiry.split("-")
    if len(parts) == 3:
        month_num = int(parts[1])
        months = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
        if 1 <= month_num <= 12:
            month = months[month_num - 1]
            year = parts[0][2:]  # Last 2 digits
            strike_str = str(int(strike)) if strike == int(strike) else str(strike)
            return f"{underlying}{year}{month}{strike_str}{option_type}"
    return underlying


def _compact_future_symbol(underlying: str, expiry: str) -> str:
    """Build compact future symbol like 'NIFTY26JUNFUT'."""
    parts = expiry.split("-")
    if len(parts) == 3:
        month_num = int(parts[1])
        months = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
        if 1 <= month_num <= 12:
            month = months[month_num - 1]
            year = parts[0][2:]
            return f"{underlying}{year}{month}FUT"
    return underlying


__all__ = [
    "InstrumentNotFoundError",
    "InstrumentResolver",
    "InMemoryInstrumentResolver",
    "ResolvedInstrument",
]
