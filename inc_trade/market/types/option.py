"""Option instrument subclass."""

from __future__ import annotations

from decimal import Decimal

from inc_trade.market.instrument import Instrument


class Option(Instrument):
    """Option instrument with Greeks and chain access.

    Fields ``strike``, ``option_type``, and ``expiry`` are inherited
    from the base :class:`Instrument` dataclass.
    """

    def greeks(self) -> dict:
        """Option Greeks from cached quote state.

        Returns an empty dict for non-option instruments.
        """
        if not self.is_option():
            return {}
        try:
            state = self.quote_state()
        except Exception:
            return {}
        return {
            "iv": None,
            "delta": None,
            "theta": None,
            "gamma": None,
            "vega": None,
            "ltp": getattr(state, "ltp", Decimal("0")),
            "oi": getattr(state, "oi", 0),
            "volume": getattr(state, "volume", 0),
        }

    def option_chain(self, expiry: str | None = None):
        """Option chain for the underlying instrument.

        Args:
            expiry: Expiry date string (e.g., ``"2025-01-30"``).
                    ``None`` uses the nearest expiry.

        Returns:
            :class:`OptionChain` domain entity.

        Raises:
            RuntimeError: If the instrument has no market data context.
        """
        ctx = getattr(self, "_context", None) or getattr(self, "_delegate_context", None)
        if ctx:
            return ctx.option_chain(self.symbol, self.exchange, expiry)
        raise RuntimeError("Instrument has no market data context")
