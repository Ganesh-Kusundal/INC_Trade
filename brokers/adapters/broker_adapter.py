"""BrokerAdapter protocol — primary broker interface for provider injection.

A ``BrokerAdapter`` implements the provider protocols directly so that
it can be injected into ``Instrument`` objects. Unlike the gateway pattern
(which exposes properties like ``.orders``, ``.market_data``), an adapter
IS the provider — it directly implements ``quote()``, ``depth()``,
``place_order()``, etc.

Usage::

    from brokers.adapters.dhan import DhanAdapter

    adapter = DhanAdapter(client_id="123", access_token="abc")
    adapter.connect()

    # Instrument-centric API
    inst = adapter.instrument("RELIANCE", "NSE", apply_depth=200)
    inst.quote()        # → Quote via adapter
    inst.depth(200)     # → 200-level depth via adapter
    inst.buy(qty=10)    # → OrderResponse via adapter
    inst.subscribe(cb)  # → StreamHandle via adapter
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from brokers.domain.enums import Side
from brokers.ports.providers import (
    DepthProvider,
    HistoricalDataProvider,
    InstrumentDataProvider,
    OrderProvider,
    StreamingDataProvider,
)

if TYPE_CHECKING:
    from datetime import datetime

    from brokers.domain.entities import Candle, MarketDepth, Quote
    from brokers.market.instrument import Instrument


@runtime_checkable
class BrokerAdapter(
    InstrumentDataProvider,
    DepthProvider,
    HistoricalDataProvider,
    StreamingDataProvider,
    OrderProvider,
    Protocol,
):
    """Primary broker interface — replaces BrokerGateway.

    Combines all provider protocols into a single interface that can be
    injected directly into Instruments. The adapter handles connect/
    disconnect lifecycle and provides a factory for creating Instruments.

    .. seealso::
        :class:`DhanAdapter`
        :class:`UpstoxAdapter`
        :class:`PaperAdapter`
    """

    @property
    def broker_id(self) -> str:
        """Unique broker identifier (e.g., 'dhan', 'upstox', 'paper')."""
        ...

    def connect(self, **credentials: Any) -> None:
        """Establish connection to the broker.

        Args:
            **credentials: Broker-specific credentials (access_token,
                client_id, etc.).
        """
        ...

    def disconnect(self) -> None:
        """Close connection to the broker and release resources."""
        ...

    def instrument(
        self,
        symbol: str,
        exchange: str,
        **kwargs: Any,
    ) -> Instrument:
        """Create an Instrument with this adapter injected as provider.

        The returned Instrument has this adapter wired as its quote,
        depth, historical, streaming, and order provider. Additional
        kwargs are forwarded to :meth:`InstrumentFactory.create`.

        Args:
            symbol: Trading symbol (e.g., 'RELIANCE').
            exchange: Exchange code (e.g., 'NSE', 'NFO').

        Returns:
            An Instrument (possibly wrapped in decorators) ready for
            live data and trading.
        """
        from brokers.market.factory import InstrumentFactory

        return InstrumentFactory.create(
            symbol=symbol,
            exchange=exchange,
            provider=self,
            depth_provider=self,
            historical_provider=self,
            streaming_provider=self,
            order_provider=self,
            **kwargs,
        )

    # ── InstrumentDataProvider ────────────────────────────────────────

    def quote(self, symbol: str, exchange: str) -> Quote: ...
    def ltp(self, symbol: str, exchange: str) -> Decimal: ...
    def depth(self, symbol: str, exchange: str, levels: int = 5) -> MarketDepth: ...
    def quote_batch(self, symbols: list[str], exchange: str) -> dict[str, Quote]: ...

    # ── DepthProvider ─────────────────────────────────────────────────

    @property
    def max_levels(self) -> int:
        """Maximum depth levels this adapter supports."""
        ...

    # ── HistoricalDataProvider ────────────────────────────────────────

    def get_candles(
        self,
        symbol: str,
        exchange: str,
        start: datetime,
        end: datetime,
        resolution: str,
    ) -> list[Candle]: ...

    # ── StreamingDataProvider ─────────────────────────────────────────

    def subscribe(self, instrument: Any, callback: Any) -> Any: ...
    def unsubscribe(self, instrument: Any) -> None: ...

    @property
    def is_connected(self) -> bool: ...

    # ── OrderProvider ─────────────────────────────────────────────────

    def place_order(
        self,
        symbol: str,
        exchange: str,
        side: Side,
        quantity: int,
        order_type: Any = None,
        price: Decimal = Decimal("0"),
        trigger_price: Decimal = Decimal("0"),
        **kwargs: Any,
    ) -> Any: ...

    def modify_order(
        self,
        order_id: str,
        quantity: int | None = None,
        price: Decimal | None = None,
        **kwargs: Any,
    ) -> Any: ...

    def cancel_order(self, order_id: str) -> Any: ...
