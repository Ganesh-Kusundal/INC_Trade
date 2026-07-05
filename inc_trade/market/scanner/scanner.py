"""Market scanner — real-time and periodic scanning of instruments.

The Scanner consumes instruments from the InstrumentRegistry and
evaluates a ``ScanCriteria`` against current market data. It is
broker-agnostic and trading-agnostic.

Architecture rules:
- imports only from ``brokers.domain``, ``brokers.market``
- no knowledge of adapters, trading, services, or infrastructure
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from inc_trade.market.scanner.result import ScanResult

if TYPE_CHECKING:
    from collections.abc import Callable

    from inc_trade.market.scanner.criteria import ScanCriteria

logger = logging.getLogger(__name__)


class Scanner:
    """Evaluates ``ScanCriteria`` against instruments in a registry.

    Usage::

        scanner = Scanner(registry, market_data)
        result = scanner.scan(PriceAbove(Decimal("2500")))
        for inst, reason in result.matched:
            print(f"Matched: {inst.composite_key} — {reason}")
    """

    def __init__(
        self,
        registry: Any,
        market_data: Any,
    ) -> None:
        self._registry = registry
        self._market_data = market_data

    def scan(
        self,
        criteria: ScanCriteria,
        symbols: list[str] | None = None,
    ) -> ScanResult:
        """Synchronously scan instruments against the given criteria.

        Args:
            criteria: ``ScanCriteria`` instance to evaluate.
            symbols: Optional list of composite keys to restrict the
                scan to. ``None`` means scan all registered instruments.

        Returns:
            ``ScanResult`` with matched instruments and metadata.
        """
        start = time.time()
        all_instruments = self._registry.get_all()
        if symbols is not None:
            instrument_map = {k: v for k, v in all_instruments.items() if k in symbols}
        else:
            instrument_map = dict(all_instruments)

        matched: list[tuple[Any, str]] = []
        description = criteria.describe()
        for key, instrument in instrument_map.items():
            try:
                if criteria.matches(instrument, self._market_data):
                    matched.append((instrument, description))
            except Exception as exc:
                logger.debug("Scanner: criterion error on %s: %s", key, exc)

        duration_ms = (time.time() - start) * 1000.0
        return ScanResult(
            matched=matched,
            total_scanned=len(instrument_map),
            duration_ms=duration_ms,
        )

    def scan_with_callback(
        self,
        criteria: ScanCriteria,
        callback: Callable[[Any, str], None],
        symbols: list[str] | None = None,
    ) -> ScanResult:
        """Scan and invoke callback for each match.

        Args:
            criteria: ``ScanCriteria`` to evaluate.
            callback: ``(instrument, reason) -> None`` invoked per match.
            symbols: Optional symbol filter.

        Returns:
            ``ScanResult`` for the scan.
        """
        result = self.scan(criteria, symbols)
        for instrument, reason in result.matched:
            try:
                callback(instrument, reason)
            except Exception as exc:
                logger.warning("Scanner: callback error: %s", exc)
        return result
