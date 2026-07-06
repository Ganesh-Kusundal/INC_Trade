"""Dhan instrument identity — resolver and immutable reference carrier.

DhanInstrumentRef is the ONLY object that flows into a Dhan HTTP payload.
It carries the numeric security_id and wire-format segment code that Dhan
requires for every API call (orders, market data, historical).

DhanInstrumentResolver loads the Dhan master CSV and provides O(1) lookup
by (symbol, exchange) or by security_id.
"""

from __future__ import annotations

import csv
import io
import logging
import threading
from dataclasses import dataclass
from decimal import Decimal

from brokers.domain.exceptions import InstrumentNotFoundError
from brokers.domain.symbols import normalize_symbol

from brokers.adapters.dhan.config import (
    CSV_EXCHANGE_TO_SEGMENT,
    DERIVATIVE_SEGMENTS,
    DHAN_SEGMENTS,
    EXCHANGE_MAP,
    INSTRUMENT_TO_SEGMENT,
    INSTRUMENT_TYPE_MAP,
)
from brokers.adapters.dhan.index_registry import DhanIndexRegistry
from brokers.adapters.dhan.instrument_loader import InstrumentLoader

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DhanInstrumentRef:
    """Immutable carrier for Dhan-internal instrument identity.

    Validates at construction:
    - security_id must be a non-empty digit string with int value > 0
    - exchange_segment must be in DHAN_SEGMENTS
    """

    symbol: str
    security_id: str
    exchange_segment: str
    instrument_type: str = "EQUITY"
    lot_size: int = 1
    tick_size: Decimal = Decimal("0.05")

    def __post_init__(self) -> None:
        if not self.symbol or not self.symbol.strip():
            raise ValueError(f"symbol must be non-empty, got {self.symbol!r}")
        if not self.security_id or not self.security_id.isdigit():
            raise ValueError(
                f"security_id must be a positive digit string, got {self.security_id!r}"
            )
        if int(self.security_id) <= 0:
            raise ValueError(f"security_id must be > 0, got {self.security_id!r}")
        if self.exchange_segment not in DHAN_SEGMENTS:
            raise ValueError(
                f"Invalid exchange_segment: {self.exchange_segment!r}. "
                f"Must be one of {sorted(DHAN_SEGMENTS)}"
            )

    def security_id_str(self) -> str:
        return str(self.security_id)

    def security_id_int(self) -> int:
        return int(self.security_id)


class DhanInstrumentResolver:
    """Loads Dhan master CSV and resolves symbol+exchange to DhanInstrumentRef.

    Thread-safe. O(1) lookup by (symbol, exchange) or by security_id.
    """

    def __init__(self) -> None:
        self._by_symbol: dict[tuple[str, str], DhanInstrumentRef] = {}
        self._by_security_id: dict[str, DhanInstrumentRef] = {}
        self._by_underlying: dict[tuple[str, str], list[DhanInstrumentRef]] = {}
        self._loaded = False
        self._lock = threading.RLock()

    def load(self, force_refresh: bool = False) -> None:
        """Fetch and parse the Dhan master CSV (disk-cached via InstrumentLoader)."""
        with self._lock:
            if self._loaded and not force_refresh:
                return
            csv_text = InstrumentLoader.load_csv_text(force_refresh=force_refresh)
            self._parse_csv_text(csv_text)
            self._loaded = True

    def _parse_csv_text(self, csv_text: str) -> None:
        self._by_symbol.clear()
        self._by_security_id.clear()
        self._by_underlying.clear()
        reader = csv.DictReader(io.StringIO(csv_text))
        count = 0
        for row in reader:
            ref = self._row_to_ref(row)
            if ref is None:
                continue
            key = (ref.symbol.upper(), ref.exchange_segment)
            self._by_symbol[key] = ref
            self._by_security_id[ref.security_id] = ref
            underlying = (
                (row.get("SM_SYMBOL_NAME") or row.get("SEM_SYMBOL_NAME") or "").strip().upper()
            )
            if underlying and ref.instrument_type.startswith(("FUT", "OPT")):
                ukey = (underlying, ref.exchange_segment)
                self._by_underlying.setdefault(ukey, []).append(ref)
            count += 1
        logger.info("dhan_instruments_loaded", extra={"count": count})

    @staticmethod
    def _row_to_ref(row: dict[str, str]) -> DhanInstrumentRef | None:
        symbol = (row.get("SEM_TRADING_SYMBOL") or "").strip()
        security_id = (row.get("SEM_SMST_SECURITY_ID") or "").strip()
        if not symbol or not security_id:
            return None
        # security_id may be a digit-only string; strip any decimal part first
        security_id = security_id.split(".")[0]
        if not security_id.isdigit() or int(security_id) <= 0:
            return None

        # CSV uses plain exchange codes: "NSE", "BSE", "MCX"
        exchange_code = (row.get("SEM_EXM_EXCH_ID") or "").strip().upper()
        segment = CSV_EXCHANGE_TO_SEGMENT.get(exchange_code)
        if segment is None:
            return None

        instrument_name = (row.get("SEM_INSTRUMENT_NAME") or "").strip().upper()
        instrument_type = INSTRUMENT_TYPE_MAP.get(instrument_name, "EQUITY")

        # Derivative instrument types override the base segment (e.g. NSE OPTIDX → NSE_FNO)
        if instrument_name in INSTRUMENT_TO_SEGMENT:
            segment = INSTRUMENT_TO_SEGMENT[instrument_name]
        elif instrument_name == "INDEX":
            segment = "IDX_I"

        # lot_size in CSV is a float string like "1.0" or "75.0"
        lot_size_raw = row.get("SEM_LOT_UNITS") or "1"
        try:
            lot_size = int(float(lot_size_raw))
        except (TypeError, ValueError):
            lot_size = 1

        tick_raw = row.get("SEM_TICK_SIZE") or "0.05"
        try:
            tick_size = Decimal(str(float(tick_raw)))
        except (TypeError, ValueError):
            tick_size = Decimal("0.05")

        try:
            return DhanInstrumentRef(
                symbol=symbol,
                security_id=security_id,
                exchange_segment=segment,
                instrument_type=instrument_type,
                lot_size=max(lot_size, 1),
                tick_size=tick_size,
            )
        except ValueError:
            return None

    def resolve(
        self,
        symbol: str,
        exchange: str,
        *,
        expected_segment: str | None = None,
    ) -> DhanInstrumentRef:
        """Resolve symbol+exchange to a DhanInstrumentRef.

        Accepts user-facing exchange names ("NSE", "NFO", "MCX", "BSE", "BFO")
        or direct segment codes ("NSE_EQ", "NSE_FNO", "MCX_COMM").
        Raises InstrumentNotFoundError if not found.

        When ``expected_segment`` is set, rejects index fallback for derivative
        queries (PR-C) and fails if the resolved segment does not match.
        """
        if not self._loaded:
            self.load()

        symbol_upper = symbol.strip().upper()
        if not symbol_upper:
            raise InstrumentNotFoundError(symbol)

        exchange_upper = exchange.strip().upper()
        segment = EXCHANGE_MAP.get(exchange_upper, exchange_upper)

        ref = self._lookup(symbol_upper, segment, expected_segment=expected_segment)
        if ref is not None:
            return ref

        exchange_prefix = exchange_upper.split("_")[0]
        with self._lock:
            for (sym, seg), candidate in self._by_symbol.items():
                if sym == symbol_upper and seg.startswith(exchange_prefix):
                    return self._finalize_ref(candidate, expected_segment, source="prefix_scan")

        raise InstrumentNotFoundError(symbol)

    def _lookup(
        self,
        symbol: str,
        segment: str,
        *,
        expected_segment: str | None = None,
    ) -> DhanInstrumentRef | None:
        """Progressive symbol lookup — archive resolver parity."""
        keys = self._symbol_lookup_keys(normalize_symbol(symbol))
        with self._lock:
            for key_sym in keys:
                ref = self._by_symbol.get((key_sym, segment))
                if ref is not None:
                    return self._finalize_ref(ref, expected_segment, source="direct")

            if DhanIndexRegistry.lookup(keys[0]) is not None and segment != "IDX_I":
                for key_sym in keys:
                    ref = self._by_symbol.get((key_sym, "IDX_I"))
                    if ref is not None:
                        return self._finalize_ref(
                            ref, expected_segment, source="index_exchange_fallback"
                        )

        index_entry = DhanIndexRegistry.lookup(keys[0])
        if index_entry is not None and index_entry.security_id:
            synthetic = DhanInstrumentRef(
                symbol=keys[0],
                security_id=index_entry.security_id,
                exchange_segment=index_entry.dhan_segment,
                instrument_type="EQUITY",
            )
            logger.info(
                "index_resolved_via_hardcoded_id",
                extra={
                    "symbol": keys[0],
                    "security_id": index_entry.security_id,
                },
            )
            return self._finalize_ref(synthetic, expected_segment, source="hardcoded_index")
        return None

    @staticmethod
    def _symbol_lookup_keys(clean: str) -> list[str]:
        """Generate progressive lookup keys (stripped, CALL→CE, PUT→PE)."""
        keys: list[str] = [clean]
        stripped = clean.replace(" ", "").replace("-", "").replace("_", "")
        if stripped != clean:
            keys.append(stripped)
        if clean.endswith("CALL"):
            ce = clean[:-4] + "CE"
            keys.append(ce)
            stripped_ce = ce.replace(" ", "").replace("-", "").replace("_", "")
            if stripped_ce != ce:
                keys.append(stripped_ce)
        elif clean.endswith("PUT"):
            pe = clean[:-3] + "PE"
            keys.append(pe)
            stripped_pe = pe.replace(" ", "").replace("-", "").replace("_", "")
            if stripped_pe != pe:
                keys.append(stripped_pe)
        seen: set[str] = set()
        ordered: list[str] = []
        for key in keys:
            if key not in seen:
                seen.add(key)
                ordered.append(key)
        return ordered

    def _finalize_ref(
        self,
        ref: DhanInstrumentRef,
        expected_segment: str | None,
        *,
        source: str,
    ) -> DhanInstrumentRef:
        """Apply expected_segment guard and emit audit log."""
        if expected_segment in DERIVATIVE_SEGMENTS and ref.exchange_segment == "IDX_I":
            raise InstrumentNotFoundError(
                f"{ref.symbol}: resolved to index segment IDX_I but caller expected "
                f"derivative segment {expected_segment!r}"
            )
        if expected_segment is not None and ref.exchange_segment != expected_segment:
            raise InstrumentNotFoundError(
                f"{ref.symbol}: resolved to segment {ref.exchange_segment!r} but "
                f"caller required {expected_segment!r}"
            )
        logger.info(
            "security_id_issued",
            extra={
                "symbol": ref.symbol,
                "security_id": ref.security_id,
                "exchange_segment": ref.exchange_segment,
                "source": source,
                "expected_segment": expected_segment,
            },
        )
        return ref

    def get_by_security_id(self, security_id: str) -> DhanInstrumentRef | None:
        """Reverse lookup by security_id."""
        if not self._loaded:
            self.load()
        with self._lock:
            return self._by_security_id.get(str(security_id))

    def search(self, query: str, limit: int = 10) -> list[DhanInstrumentRef]:
        """Substring search on symbol."""
        if not self._loaded:
            self.load()
        query_upper = query.upper()
        results: list[DhanInstrumentRef] = []
        seen: set[str] = set()
        with self._lock:
            for ref in self._by_security_id.values():
                if query_upper in ref.symbol.upper() and ref.security_id not in seen:
                    results.append(ref)
                    seen.add(ref.security_id)
                    if len(results) >= limit:
                        break
        return results

    def get_futures(self, underlying: str, exchange: str) -> list[DhanInstrumentRef]:
        """Return futures contracts for an underlying, sorted by symbol."""
        if not self._loaded:
            self.load()
        segment = EXCHANGE_MAP.get(exchange.strip().upper(), exchange.strip().upper())
        key = (underlying.strip().upper(), segment)
        with self._lock:
            refs = list(self._by_underlying.get(key, []))
        return sorted(
            (r for r in refs if r.instrument_type.startswith("FUT")),
            key=lambda r: r.symbol,
        )

    def load_from_csv_text(self, csv_text: str) -> None:
        """Load from a CSV string (for testing)."""
        with self._lock:
            self._parse_csv_text(csv_text)
            self._loaded = True
            logger.info(
                "dhan_instruments_loaded_from_text",
                extra={"count": len(self._by_security_id)},
            )
