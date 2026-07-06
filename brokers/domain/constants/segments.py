"""Segment-to-exchange mapping constants and resolution."""

from __future__ import annotations

SEGMENT_TO_EXCHANGE: dict[str, str] = {
    "NSE_EQ": "NSE",
    "NSE_FNO": "NFO",
    "NSE_CURRENCY": "NSE",
    "BSE_EQ": "BSE",
    "BSE_FNO": "BFO",
    "BSE_CURRENCY": "BSE",
    "MCX_COMM": "MCX",
}


class SegmentResolver:
    """Maps broker wire segment codes ↔ user-facing exchange codes.

    Canonical mappings live in :data:`SEGMENT_TO_EXCHANGE`. Broker adapters
    supply optional override tables for broker-specific segment codes.
    """

    def __init__(
        self,
        *,
        segment_to_exchange_overrides: dict[str, str] | None = None,
        exchange_to_segment: dict[str, str] | None = None,
    ) -> None:
        self._segment_to_exchange = {
            **SEGMENT_TO_EXCHANGE,
            **(segment_to_exchange_overrides or {}),
        }
        self._exchange_to_segment = {
            k.upper(): v.upper() for k, v in (exchange_to_segment or {}).items()
        }

    @property
    def segment_to_exchange(self) -> dict[str, str]:
        return dict(self._segment_to_exchange)

    def to_exchange(self, segment: str) -> str:
        key = segment.strip().upper()
        return self._segment_to_exchange.get(key, key)

    def to_segment(self, exchange: str) -> str:
        key = exchange.strip().upper()
        if self._exchange_to_segment:
            return self._exchange_to_segment.get(key, key)
        for seg, ex in self._segment_to_exchange.items():
            if ex == key:
                return seg
        return key
