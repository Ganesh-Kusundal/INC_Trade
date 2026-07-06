"""Futures instrument subclass."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from brokers_core.market.instrument import Instrument


@dataclass(frozen=True)
class Future(Instrument):
    """Futures instrument with expiry management.

    .. note::
        ``underlying`` and ``contract_size`` are proper dataclass fields
        (not class-level annotations). They participate in ``__init__``,
        ``__eq__``, and ``__hash__`` alongside the base Instrument fields.
    """

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
        ctx = getattr(self, "_context", None)
        if ctx:
            try:
                spot = ctx.ltp(self.underlying, self.exchange)
                return self.ltp() - spot
            except Exception:
                return Decimal("0")
        return Decimal("0")
