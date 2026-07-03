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

import requests

from brokers.adapters.dhan.config import (
    CSV_EXCHANGE_TO_SEGMENT,
    DHAN_SEGMENTS,
    ENDPOINTS,
    EXCHANGE_MAP,
    INSTRUMENT_TO_SEGMENT,
    INSTRUMENT_TYPE_MAP,
)
from brokers.domain.exceptions import InstrumentNotFoundError

logger = logging.getLogger(__name__)

_CSV_URL = ENDPOINTS["instruments"]


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
        self._loaded = False
        self._lock = threading.RLock()

    def load(self) -> None:
        """Fetch and parse the Dhan master CSV."""
        with self._lock:
            if self._loaded:
                return
            self._do_load()
            self._loaded = True

    def _do_load(self) -> None:
        resp = requests.get(_CSV_URL, timeout=30)
        resp.raise_for_status()
        reader = csv.DictReader(io.StringIO(resp.text))
        count = 0
        for row in reader:
            ref = self._row_to_ref(row)
            if ref is None:
                continue
            key = (ref.symbol.upper(), ref.exchange_segment)
            self._by_symbol[key] = ref
            self._by_security_id[ref.security_id] = ref
            count += 1
        logger.info("dhan_instruments_loaded", extra={"count": count})

    @staticmethod
    def _row_to_ref(row: dict) -> DhanInstrumentRef | None:
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

        try:
            return DhanInstrumentRef(
                symbol=symbol,
                security_id=security_id,
                exchange_segment=segment,
                instrument_type=instrument_type,
                lot_size=max(lot_size, 1),
            )
        except ValueError:
            return None

    def resolve(self, symbol: str, exchange: str) -> DhanInstrumentRef:
        """Resolve symbol+exchange to a DhanInstrumentRef.

        Accepts user-facing exchange names ("NSE", "NFO", "MCX", "BSE", "BFO")
        or direct segment codes ("NSE_EQ", "NSE_FNO", "MCX_COMM").
        Raises InstrumentNotFoundError if not found.
        """
        if not self._loaded:
            self.load()

        symbol_upper = symbol.strip().upper()
        if not symbol_upper:
            raise InstrumentNotFoundError(symbol)

        exchange_upper = exchange.strip().upper()
        # Translate user-facing exchange alias → segment code
        segment = EXCHANGE_MAP.get(exchange_upper, exchange_upper)

        key = (symbol_upper, segment)
        with self._lock:
            ref = self._by_symbol.get(key)
        if ref is not None:
            return ref

        # Broader scan: match symbol across all segments within the exchange family
        # e.g. user asks ("NIFTY", "NSE") but it lives in NSE_FNO
        exchange_prefix = exchange_upper.split("_")[0]  # "NSE_FNO" → "NSE"
        with self._lock:
            for (sym, seg), candidate in self._by_symbol.items():
                if sym == symbol_upper and seg.startswith(exchange_prefix):
                    return candidate

        raise InstrumentNotFoundError(symbol)

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

    def load_from_csv_text(self, csv_text: str) -> None:
        """Load from a CSV string (for testing)."""
        with self._lock:
            self._by_symbol.clear()
            self._by_security_id.clear()
            reader = csv.DictReader(io.StringIO(csv_text))
            count = 0
            for row in reader:
                ref = self._row_to_ref(row)
                if ref is None:
                    continue
                key = (ref.symbol.upper(), ref.exchange_segment)
                self._by_symbol[key] = ref
                self._by_security_id[ref.security_id] = ref
                count += 1
            self._loaded = True
            logger.info("dhan_instruments_loaded_from_text", extra={"count": count})
