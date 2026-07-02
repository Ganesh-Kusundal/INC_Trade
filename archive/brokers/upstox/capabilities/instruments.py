"""Instruments capability group for Upstox."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class InstrumentsCapability:
    """Symbol resolution, instrument master, and search."""

    instrument_resolver: Any
    instrument_loader: Any
    instrument_search: Any

    def resolve(self, *args: Any, **kwargs: Any) -> Any:
        return self.instrument_resolver.resolve(*args, **kwargs)

    def search(self, *args: Any, **kwargs: Any) -> Any:
        return self.instrument_search.search(*args, **kwargs)
