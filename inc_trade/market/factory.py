"""InstrumentFactory — creates the correct Instrument subclass."""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from typing import Any

from inc_trade.domain.symbols import normalize_symbol
from inc_trade.market.instrument import Instrument
from inc_trade.market.types.equity import Equity
from inc_trade.market.types.future import Future
from inc_trade.market.types.index import Index
from inc_trade.market.types.option import Option

_DERIVATIVE_EXCHANGES = {"NFO", "BFO", "CDS", "BCD"}
_OPTION_SUFFIXES = {"CE", "PE"}


def _is_index(symbol: str) -> bool:
    try:
        from inc_trade.config.indices import is_index

        return is_index(symbol)
    except ImportError:
        return False


def _extract_underlying(symbol: str) -> str:
    """Extract underlying from a futures symbol like NIFTY26JUNFUT -> NIFTY."""
    match = re.match(r"^([A-Z]+)", symbol)
    return match.group(1) if match else symbol


class InstrumentFactory:
    """Factory responsible for creating the correct Instrument subclass.

    Usage::

        inst = InstrumentFactory.create(
            symbol="RELIANCE",
            exchange="NSE",
            context=market_data_context,
        )
    """

    @staticmethod
    def create(
        symbol: str,
        exchange: str,
        segment: str = "",
        name: str = "",
        lot_size: int = 1,
        tick_size: Decimal = Decimal("0.05"),
        isin: str = "",
        expiry: datetime | None = None,
        strike: Decimal | None = None,
        option_type: str | None = None,
        context: Any = None,
        extensions: dict[str, Any] | None = None,
        provider: Any = None,
        historical_provider: Any = None,
        streaming_provider: Any = None,
        capabilities: Any = None,
    ) -> Instrument:
        """Create the correct Instrument subclass based on content.

        Args:
            symbol: Trading symbol (e.g., ``"RELIANCE"``).
            exchange: Exchange code (e.g., ``"NSE"``, ``"NFO"``).
            segment: Market segment.
            name: Human-readable name.
            lot_size: Minimum tradeable quantity.
            tick_size: Minimum price increment.
            isin: International Securities Identification Number.
            expiry: Expiry date for derivatives.
            strike: Strike price for options.
            option_type: ``"CE"`` or ``"PE"`` for options.
            context: Market data context attached to the instrument.
            extensions: Arbitrary extension data (fundamentals, etc.).
            provider: InstrumentDataProvider protocol implementation.
            historical_provider: HistoricalDataProvider protocol implementation.
            streaming_provider: StreamingDataProvider protocol implementation.
            capabilities: InstrumentCapabilities for this instrument.

        Returns:
            An :class:`Equity`, :class:`Future`, :class:`Option`,
            or :class:`Index` instance.
        """
        sym = normalize_symbol(symbol)
        ex = exchange.upper().strip()
        is_derivative = ex in _DERIVATIVE_EXCHANGES
        opt = option_type.upper() if option_type else None

        if opt in _OPTION_SUFFIXES and strike is not None:
            inst: Instrument = Option(
                symbol=sym,
                exchange=ex,
                segment=segment,
                name=name,
                lot_size=lot_size,
                tick_size=tick_size,
                isin=isin,
                expiry=expiry,
                strike=strike,
                option_type=opt,
            )
        elif is_derivative and expiry is not None and strike is None:
            underlying = _extract_underlying(sym)
            inst = Future(
                symbol=sym,
                exchange=ex,
                segment=segment,
                name=name,
                lot_size=lot_size,
                tick_size=tick_size,
                isin=isin,
                expiry=expiry,
                underlying=underlying,
                contract_size=lot_size,
            )
        elif _is_index(sym):
            inst = Index(
                symbol=sym,
                exchange=ex,
                segment=segment,
                name=name,
                lot_size=lot_size,
                tick_size=tick_size,
                isin=isin,
            )
        else:
            inst = Equity(
                symbol=sym,
                exchange=ex,
                segment=segment,
                name=name,
                lot_size=lot_size,
                tick_size=tick_size,
                isin=isin,
            )

        # Attach non-dataclass attributes (context, extensions) so they
        # don't participate in __init__, __eq__, or __hash__.
        object.__setattr__(inst, "_context", context)
        object.__setattr__(inst, "_delegate_context", context)  # backward compat
        object.__setattr__(inst, "_extensions", extensions or {})

        # Phase 3: Rich instrument provider injection
        object.__setattr__(inst, "_provider", provider)
        object.__setattr__(inst, "_historical_provider", historical_provider)
        object.__setattr__(inst, "_streaming_provider", streaming_provider)
        object.__setattr__(inst, "_capabilities", capabilities)
        return inst
