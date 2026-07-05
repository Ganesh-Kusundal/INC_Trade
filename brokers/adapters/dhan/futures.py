"""Futures adapter — contract resolution and data."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Literal

from brokers.adapters.dhan.identity import DhanInstrumentRef, DhanInstrumentResolver
from inc_trade.ports.http_client_port import HttpClientPort

logger = logging.getLogger(__name__)

# Dhan futures symbol formats:
#   "NIFTY-31Jul2026-FUT" (day+month+year)
#   "NIFTY-Aug2026-FUT"   (month+year only)
_EXPIRY_PATTERN = re.compile(
    r"^(?P<underlying>.+?)-(?P<expiry>\d{2}[A-Za-z]{3}\d{4}|[A-Za-z]{3}\d{4})-",
    re.IGNORECASE,
)

_MONTH_MAP = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
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
    expiry_str = m.group("expiry")
    try:
        if expiry_str[0].isdigit():
            day = int(expiry_str[:2])
            month_abbr = expiry_str[2:5].lower()
            year = int(expiry_str[5:])
        else:
            day = 1
            month_abbr = expiry_str[:3].lower()
            year = int(expiry_str[3:])
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
        client: HttpClientPort,
        resolver: DhanInstrumentResolver,
    ) -> None:
        self._client = client
        self._resolver = resolver

    def _iter_futures_refs(self, underlying: str) -> list[DhanInstrumentRef]:
        """Scan loaded instruments for futures matching *underlying* prefix."""
        query = underlying.strip().upper()
        if not self._resolver._loaded:
            self._resolver.load()
        prefix = f"{query}-"
        matches: list[DhanInstrumentRef] = []
        with self._resolver._lock:
            for ref in self._resolver._by_security_id.values():
                if ref.instrument_type not in FUTURES_INSTRUMENT_TYPES:
                    continue
                sym = ref.symbol.upper()
                if sym == query or sym.startswith(prefix):
                    matches.append(ref)
        return matches

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
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        futures_with_expiry: list[tuple[datetime, DhanInstrumentRef]] = []
        for ref in self._iter_futures_refs(underlying):
            expiry = _parse_expiry(ref.symbol)
            if expiry is None:
                continue
            if expiry < now:
                continue
            futures_with_expiry.append((expiry, ref))

        if not futures_with_expiry:
            logger.warning(
                "futures_not_found",
                extra={"underlying": underlying, "exchange": exchange},
            )
            return None

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
        """Return all active futures contracts for an underlying, sorted by expiry."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        futures_with_expiry: list[tuple[datetime, DhanInstrumentRef]] = []
        for ref in self._iter_futures_refs(underlying):
            expiry = _parse_expiry(ref.symbol)
            if expiry is None:
                continue
            if expiry < now:
                continue
            futures_with_expiry.append((expiry, ref))

        futures_with_expiry.sort(key=lambda x: x[0])
        return [ref for _, ref in futures_with_expiry]
