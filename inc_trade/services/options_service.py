"""Options service — domain layer for options derivatives data."""

from __future__ import annotations

import logging
from typing import Any

from inc_trade.domain.entities import OptionChain
from inc_trade.ports.options import OptionsPort

logger = logging.getLogger(__name__)


class OptionsService:
    """Domain service for options derivatives data.

    Encapsulates business rules for option chain and expiry lookup.
    """

    def __init__(self, options_port: OptionsPort | None = None) -> None:
        """Initialize with an options port."""
        self._options_port = options_port

    def get_expiries(self, underlying: str, exchange: str = "NFO") -> list[str]:
        """Get available expiry dates for an underlying."""
        if self._options_port is None:
            from inc_trade.domain.exceptions import NotSupportedError
            raise NotSupportedError("Options not supported by this broker")
        return self._options_port.get_expiries(underlying=underlying, exchange=exchange)

    def get_option_chain(
        self,
        underlying: str,
        exchange: str = "NFO",
        expiry: str | None = None,
    ) -> OptionChain:
        """Get the full option chain for a specific expiry."""
        if self._options_port is None:
            from inc_trade.domain.exceptions import NotSupportedError
            raise NotSupportedError("Options not supported by this broker")
        return self._options_port.get_option_chain(
            underlying=underlying,
            exchange=exchange,
            expiry=expiry,
        )
