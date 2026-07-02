"""Dhan instruments — InstrumentPort backed by DhanInstrumentResolver."""

from __future__ import annotations

from brokers.adapters.dhan.config import SEGMENT_TO_EXCHANGE
from brokers.adapters.dhan.identity import DhanInstrumentResolver
from brokers.ports.instruments import InstrumentInfo


class DhanInstruments:
    """InstrumentPort implementation backed by DhanInstrumentResolver.

    Converts DhanInstrumentRef (Dhan-internal) to InstrumentInfo (broker-agnostic)
    at the boundary. No security_id leaks out.
    """

    def __init__(self, resolver: DhanInstrumentResolver) -> None:
        self._resolver = resolver

    def load(self) -> None:
        self._resolver.load()

    def search(self, query: str, limit: int = 10) -> list[InstrumentInfo]:
        refs = self._resolver.search(query, limit=limit)
        return [self._ref_to_info(ref) for ref in refs]

    def resolve(self, symbol: str, exchange: str = "NSE") -> InstrumentInfo | None:
        try:
            ref = self._resolver.resolve(symbol, exchange)
        except Exception:
            return None
        return self._ref_to_info(ref)

    @staticmethod
    def _ref_to_info(ref) -> InstrumentInfo:
        exchange = SEGMENT_TO_EXCHANGE.get(ref.exchange_segment, ref.exchange_segment)
        return InstrumentInfo(
            symbol=ref.symbol,
            exchange=exchange,
            segment=ref.exchange_segment,
            name=ref.symbol,
            lot_size=ref.lot_size,
        )
