"""Equity instrument subclass."""

from __future__ import annotations

from decimal import Decimal

from inc_trade.market.instrument import Instrument


class Equity(Instrument):
    """Equity (stock) instrument."""

    def fundamentals(self) -> dict:
        """Return fundamental data for this equity.

        Fetched from the ``fundamentals`` extension attached by the
        broker adapter.
        """
        ext = self._extension("fundamentals")
        if ext:
            return ext.get(self.symbol, self.exchange)
        return {}

    @property
    def dividend_yield(self) -> Decimal:
        """Dividend yield percentage."""
        return self.fundamentals().get("dividend_yield", Decimal("0"))

    @property
    def pe_ratio(self) -> Decimal:
        """Price-to-earnings ratio."""
        return self.fundamentals().get("pe_ratio", Decimal("0"))

    @property
    def market_cap(self) -> Decimal:
        """Market capitalisation."""
        return self.fundamentals().get("market_cap", Decimal("0"))
