"""Futures instrument subclass."""

from __future__ import annotations

from decimal import Decimal

from inc_trade.market.instrument import Instrument


class Future(Instrument):
    """Futures instrument with expiry management."""

    underlying: str = ""
    contract_size: int = 1

    def open_interest(self) -> int:
        """Open interest from cached quote state."""
        try:
            state = self.quote_state()
            return int(getattr(state, "oi", 0) or 0)
        except Exception:
            return 0

    def basis(self) -> Decimal:
        """Basis = futures LTP − spot LTP of the underlying.

        Returns ``Decimal("0")`` if the underlying cannot be resolved.
        """
        if not self.underlying:
            return Decimal("0")
        ctx = getattr(self, "_context", None) or getattr(self, "_delegate_context", None)
        if ctx:
            try:
                spot = ctx.ltp(self.underlying, self.exchange)
                return self.ltp() - spot
            except Exception:
                return Decimal("0")
        return Decimal("0")
