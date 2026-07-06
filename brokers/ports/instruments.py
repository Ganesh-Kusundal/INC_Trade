"""Instruments port — symbol resolution and instrument lookup.

Narrow interface (ISP) for instrument management. Broker adapters
implement this to provide symbol search and resolution.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from brokers.domain.constants.exchanges import DEFAULT_EQUITY_EXCHANGE
from brokers.domain.entities import InstrumentInfo

__all__ = ["InstrumentInfo", "InstrumentPort"]


@runtime_checkable
class InstrumentPort(Protocol):
    def search(self, query: str, limit: int = 10) -> list[InstrumentInfo]: ...
    def resolve(
        self, symbol: str, exchange: str = DEFAULT_EQUITY_EXCHANGE
    ) -> InstrumentInfo | None: ...
    def load(self) -> None: ...
