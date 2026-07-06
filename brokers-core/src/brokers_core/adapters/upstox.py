"""UpstoxAdapter — wraps UpstoxGateway into the BrokerAdapter protocol.

Usage::

    from inc_trade.adapters.upstox import UpstoxAdapter

    adapter = UpstoxAdapter(access_token="abc")
    adapter.connect()

    # Instrument-centric API
    inst = adapter.instrument("RELIANCE", "NSE", apply_depth=30)
    inst.quote()     # → Quote via Upstox API
    inst.depth(30)   # → 30-level depth
    inst.buy(qty=10) # → OrderResponse
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from inc_trade.adapters.broker_adapter import BrokerAdapter

if TYPE_CHECKING:
    from datetime import datetime

    from inc_trade.domain.entities import Candle, MarketDepth, Quote

logger = logging.getLogger(__name__)


class UpstoxAdapter(BrokerAdapter):
    """Upstox broker adapter implementing BrokerAdapter protocol.

    Wraps the existing UpstoxGateway and its sub-services into a single
    adapter that can be injected directly into Instruments.

    Capabilities:
        - Depth up to 30 levels (max_levels=30)
        - Full historical, streaming, and order support
        - Automatically applies Depth30Decorator via ``apply_depth=30``

    Args:
        access_token: Upstox API access token.
        **kwargs: Additional gateway kwargs (settings overrides, etc.).
    """

    def __init__(
        self,
        access_token: str | None = None,
        **kwargs: Any,
    ) -> None:
        self._access_token = access_token
        self._gateway_kwargs = kwargs
        self._gw: Any = None

    @property
    def broker_id(self) -> str:
        return "upstox"

    @property
    def max_levels(self) -> int:
        return 30

    @property
    def is_connected(self) -> bool:
        if self._gw is None:
            return False
        streaming = getattr(self._gw, "streaming", None)
        if streaming is not None:
            return streaming.is_connected
        return True

    def connect(self, **credentials: Any) -> None:
        """Create and configure the UpstoxGateway."""
        from brokers.adapters.upstox.gateway import UpstoxGateway

        token = credentials.get("access_token", self._access_token)

        self._gw = UpstoxGateway(
            access_token=token,
            **self._gateway_kwargs,
        )
        logger.info("UpstoxAdapter connected")

    def disconnect(self) -> None:
        """Close the gateway and release resources."""
        if self._gw is not None:
            self._gw.close()
            self._gw = None
            logger.info("UpstoxAdapter disconnected")

    # ── InstrumentDataProvider ────────────────────────────────────────

    def quote(self, symbol: str, exchange: str = "NSE") -> Quote:
        self._require_gateway()
        return self._gw.market_data.quote(symbol, exchange)

    def ltp(self, symbol: str, exchange: str = "NSE") -> Decimal:
        self._require_gateway()
        return self._gw.market_data.ltp(symbol, exchange)

    def quote_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Quote]:
        self._require_gateway()
        return self._gw.market_data.quote_batch(symbols, exchange)

    # ── DepthProvider (also satisfies InstrumentDataProvider.depth) ──

    def depth(self, symbol: str, exchange: str = "NSE", levels: int = 5) -> MarketDepth:
        """Get market depth with up to 30 levels.

        The underlying Upstox gateway supports up to 30 levels via WebSocket.
        """
        self._require_gateway()
        return self._gw.market_data.depth(symbol, exchange)

    # ── HistoricalDataProvider ────────────────────────────────────────

    def get_candles(
        self,
        symbol: str,
        exchange: str,
        start: datetime,
        end: datetime,
        resolution: str,
    ) -> list[Candle]:
        self._require_gateway()
        return self._gw.historical.get_historical_candles(
            symbol,
            exchange,
            start,
            end,
            resolution,
        )

    # ── StreamingDataProvider ─────────────────────────────────────────

    def subscribe(self, instrument: Any, callback: Any) -> Any:
        self._require_gateway()
        return self._gw.streaming.subscribe(instrument, callback)

    def unsubscribe(self, instrument: Any) -> None:
        self._require_gateway()
        self._gw.streaming.unsubscribe(instrument)

    # ── OrderProvider ─────────────────────────────────────────────────

    def place_order(
        self,
        symbol: str,
        exchange: str,
        side: str,
        quantity: int,
        order_type: Any = None,
        price: Decimal = Decimal("0"),
        trigger_price: Decimal = Decimal("0"),
        **kwargs: Any,
    ) -> Any:
        self._require_gateway()
        from inc_trade.domain.enums import Side

        side_enum = Side.BUY if side.upper() == "BUY" else Side.SELL
        return self._gw.orders.place_order(
            symbol=symbol,
            exchange=exchange,
            side=side_enum,
            quantity=quantity,
            order_type=order_type,
            price=price,
            trigger_price=trigger_price,
            **kwargs,
        )

    def modify_order(
        self,
        order_id: str,
        quantity: int | None = None,
        price: Decimal | None = None,
        **kwargs: Any,
    ) -> Any:
        self._require_gateway()
        return self._gw.orders.modify_order(
            order_id=order_id,
            quantity=quantity,
            price=price,
        )

    def cancel_order(self, order_id: str) -> Any:
        self._require_gateway()
        return self._gw.orders.cancel_order(order_id)

    # ── Instrument Factory ────────────────────────────────────────────

    def instrument(self, symbol: str, exchange: str, **kwargs: Any) -> Any:
        """Create an Instrument with this adapter as provider.

        Automatically applies ``apply_depth=30`` for Upstox's max depth
        capability unless explicitly overridden.
        """
        if "apply_depth" not in kwargs:
            kwargs["apply_depth"] = 30
        return super().instrument(symbol, exchange, **kwargs)

    # ── Internals ─────────────────────────────────────────────────────

    def _require_gateway(self) -> None:
        if self._gw is None:
            raise RuntimeError("UpstoxAdapter not connected. Call adapter.connect() first.")
