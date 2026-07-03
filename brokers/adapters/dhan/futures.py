"""Futures adapter — contract resolution and data."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Literal

from brokers.adapters.dhan.http import DhanHttpClient
from brokers.adapters.dhan.identity import DhanInstrumentRef, DhanInstrumentResolver

logger = logging.getLogger(__name__)

# Dhan futures symbol format in CSV: "SILVER-03Jul2026-FUT", "NIFTY-31Jul2026-FUT"
# MCX options: "SILVER-28Jul2026-272000-CE"
_EXPIRY_PATTERN = re.compile(
    r"^(?P<underlying>.+?)-(?P<expiry>\d{2}[A-Za-z]{3}\d{4})-",
    re.IGNORECASE,
)

_MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

FUTURES_INSTRUMENT_TYPES = frozenset({"FUTIDX", "FUTSTK", "FUTCOM", "FUTCUR"})


def _parse_expiry(symbol: str) -> datetime | None:
    """Parse expiry date from Dhan futures/options symbol.

    Handles format: SILVER-03Jul2026-FUT, NIFTY-31Jul2026-FUT
    Returns datetime or None if unparseable.
    """
    m = _EXPIRY_PATTERN.match(symbol)
    if not m:
        return None
    expiry_str = m.group("expiry")  # e.g. "03Jul2026"
    try:
        day = int(expiry_str[:2])
        month_abbr = expiry_str[2:5].lower()
        year = int(expiry_str[5:])
        month = _MONTH_MAP.get(month_abbr)
        if month is None:
            return None
        return datetime(year, month, day)
    except (ValueError, IndexError):
        return None


class DhanFutures:
    """Futures trading adapter for Dhan broker.

    Provides helper methods to resolve futures contracts by underlying
    and expiry date, as futures trading is otherwise handled by standard orders.
    """

    def __init__(
        self,
        client: DhanHttpClient,
        resolver: DhanInstrumentResolver,
    ) -> None:
        self._client = client
        self._resolver = resolver

    def get_contract(
        self,
        underlying: str,
        exchange: str,
        expiry_type: Literal["CURRENT", "NEXT", "FAR"] = "CURRENT",
    ) -> DhanInstrumentRef | None:
        """Resolve a futures contract by its underlying and relative expiry.

        Parameters
        ----------
        underlying : str
            Underlying symbol (e.g., "NIFTY", "SILVER", "CRUDEOIL").
        exchange : str
            Exchange code (e.g., "NSE", "NFO", "MCX").
        expiry_type : {"CURRENT", "NEXT", "FAR"}
            The relative expiry month to resolve.

        Returns
        -------
        DhanInstrumentRef | None
            The resolved futures instrument reference, or None if not found.
        """
        query = underlying.strip().upper()
        results = self._resolver.search(query, limit=500)

        # Filter to futures only matching the underlying prefix
        futures_with_expiry: list[tuple[datetime, DhanInstrumentRef]] = []
        now = datetime.utcnow()

        for ref in results:
            if ref.instrument_type not in FUTURES_INSTRUMENT_TYPES:
                continue
            if not ref.symbol.upper().startswith(query):
                continue
            expiry = _parse_expiry(ref.symbol)
            if expiry is None:
                continue
            # Only include active (non-expired) contracts
            if expiry < now:
                continue
            futures_with_expiry.append((expiry, ref))

        if not futures_with_expiry:
            logger.warning(
                "futures_not_found",
                extra={"underlying": underlying, "exchange": exchange},
            )
            return None

        # Sort by expiry date ascending: nearest first
        futures_with_expiry.sort(key=lambda x: x[0])

        index_map = {"CURRENT": 0, "NEXT": 1, "FAR": 2}
        idx = index_map.get(expiry_type, 0)

        if idx >= len(futures_with_expiry):
            logger.warning(
                "futures_expiry_not_available",
                extra={
                    "underlying": underlying,
                    "expiry_type": expiry_type,
                    "available": len(futures_with_expiry),
                },
            )
            return None

        _, ref = futures_with_expiry[idx]
        logger.info(
            "futures_contract_resolved",
            extra={
                "underlying": underlying,
                "expiry_type": expiry_type,
                "symbol": ref.symbol,
                "security_id": ref.security_id,
            },
        )
        return ref

    def get_futures_chain(
        self,
        underlying: str,
        exchange: str,
    ) -> list[DhanInstrumentRef]:
        """Return all active futures contracts for an underlying, sorted by expiry.

        Parameters
        ----------
        underlying : str
            Underlying symbol (e.g., "NIFTY", "SILVER").
        exchange : str
            Exchange code (e.g., "NSE", "MCX").

        Returns
        -------
        list[DhanInstrumentRef]
            Active futures contracts sorted nearest expiry first.
        """
        query = underlying.strip().upper()
        results = self._resolver.search(query, limit=500)
        now = datetime.utcnow()

        futures_with_expiry: list[tuple[datetime, DhanInstrumentRef]] = []
        for ref in results:
            if ref.instrument_type not in FUTURES_INSTRUMENT_TYPES:
                continue
            if not ref.symbol.upper().startswith(query):
                continue
            expiry = _parse_expiry(ref.symbol)
            if expiry is None:
                continue
            if expiry < now:
                continue
            futures_with_expiry.append((expiry, ref))

        futures_with_expiry.sort(key=lambda x: x[0])
        return [ref for _, ref in futures_with_expiry]
