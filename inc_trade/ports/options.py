"""Options port — option chain and expiry lookup.

Narrow interface (ISP) for derivatives market data. Broker adapters
implement this to provide option chains and expiry list retrieval.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from inc_trade.domain.entities import OptionChain


@runtime_checkable
class OptionsPort(Protocol):
    def get_expiries(self, underlying: str, exchange: str = "NFO") -> list[str]:
        """Get available expiry dates for an underlying."""
        ...

    def get_option_chain(
        self,
        underlying: str,
        exchange: str = "NFO",
        expiry: str | None = None,
    ) -> OptionChain:
        """Get the full option chain for a specific expiry."""
        ...
