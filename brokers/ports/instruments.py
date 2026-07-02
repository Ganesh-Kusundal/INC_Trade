"""Instruments port — symbol resolution and instrument lookup.

Narrow interface (ISP) for instrument management. Broker adapters
implement this to provide symbol search and resolution.
"""

from __future__ import annotations

from typing import Protocol


class InstrumentInfo:
    __slots__ = ("symbol", "exchange", "segment", "name", "lot_size")

    def __init__(
        self,
        symbol: str,
        exchange: str,
        segment: str = "",
        name: str = "",
        lot_size: int = 1,
    ):
        self.symbol = symbol
        self.exchange = exchange
        self.segment = segment
        self.name = name
        self.lot_size = lot_size


class InstrumentPort(Protocol):
    def search(self, query: str, limit: int = 10) -> list[InstrumentInfo]: ...
    def resolve(self, symbol: str, exchange: str = "NSE") -> InstrumentInfo | None: ...
    def load(self) -> None: ...
