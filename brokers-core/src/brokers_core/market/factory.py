"""InstrumentFactory — creates the correct Instrument subclass with providers.

The factory handles:
1. **Content-based type detection** — automatically creates ``Equity``,
   ``Future``, ``Option``, or ``Index`` based on symbol/exchange/strike.
2. **Provider injection** — wires ``_provider``, ``_depth_provider``,
   ``_order_provider``, ``_historical_provider``, ``_streaming_provider``.
3. **Decorator pipeline** — applies broker-specific extensions (depth 20,
   30, 200) via ``with_depth()``.

Usage::

    inst = InstrumentFactory.create(
        symbol="RELIANCE",
        exchange="NSE",
        provider=dhan_adapter,          # InstrumentDataProvider
        depth_provider=dhan_adapter,    # 200-level depth capable
        order_provider=dhan_adapter,    # Order placement
        apply_depth=200,                # Auto-wrap with Depth200Decorator
    )
    inst.quote()       # → Quote
    inst.depth(200)    # → 200-level MarketDepth via decorator
    inst.buy(qty=10)   # → OrderResponse via order_provider
"""

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
        depth_provider: Any = None,
        order_provider: Any = None,
        capabilities: Any = None,
        apply_depth: int = 0,
        extension_registry: Any = None,
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
            provider: InstrumentDataProvider protocol implementation (general).
            historical_provider: HistoricalDataProvider protocol implementation.
            streaming_provider: StreamingDataProvider protocol implementation.
            depth_provider: DepthProvider protocol implementation (dedicated).
            order_provider: OrderProvider protocol implementation (dedicated).
            capabilities: InstrumentCapabilities for this instrument.
            apply_depth: If > 0, auto-wrap with the depth decorator
                for the given number of levels. E.g., 200 wraps with
                ``Depth200Decorator``. Uses ``depth_provider`` or falls
                back to ``provider``.
            extension_registry: Optional ``ExtensionDecoratorRegistry``.
                If provided, decorators are applied based on adapter
                capabilities after construction. Takes precedence over
                ``apply_depth``.

        Returns:
            An :class:`Equity`, :class:`Future`, :class:`Option`,
            or :class:`Index` instance, possibly wrapped in depth decorators.
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
        object.__setattr__(inst, "_extensions", extensions or {})
        object.__setattr__(inst, "_capabilities", capabilities)

        # Provider injection via clean with_providers API
        inst = inst.with_providers(
            provider=provider,
            depth_provider=depth_provider or provider,
            historical_provider=historical_provider,
            streaming_provider=streaming_provider,
            order_provider=order_provider or provider,
        )

        # Decorator pipeline: apply depth extension if requested
        if extension_registry is not None:
            # Extension registry takes precedence — apply all registered
            # decorators based on any adapter in the provider slots.
            adapter = provider or depth_provider or order_provider
            if adapter is not None:
                inst = extension_registry.apply_from_adapter(inst, adapter)
        elif apply_depth > 0:
            from inc_trade.market.decorators import with_depth

            dp = depth_provider or provider
            inst = with_depth(inst, levels=apply_depth, depth_provider=dp)

        return inst
