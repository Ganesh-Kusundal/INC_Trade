"""DhanAdapter — wraps DhanGateway into the BrokerAdapter protocol.

Usage::

    from inc_trade.adapters.dhan import DhanAdapter

    adapter = DhanAdapter(client_id="123", access_token="abc")
    adapter.connect()

    # Instrument-centric API
    inst = adapter.instrument("RELIANCE", "NSE", apply_depth=200)
    inst.quote()     # → Quote via Dhan API
    inst.depth(200)  # → 200-level depth
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


class DhanAdapter(BrokerAdapter):
    """Dhan broker adapter implementing BrokerAdapter protocol.

    Wraps the existing DhanGateway and its sub-services into a single
    adapter that can be injected directly into Instruments.

    Capabilities:
        - Depth up to 200 levels (max_levels=200)
        - Full historical, streaming, and order support
        - Automatically applies Depth200Decorator via ``apply_depth=200``

    Args:
        client_id: Dhan client ID.
        access_token: Pre-configured access token (skips TOTP if provided).
        **kwargs: Additional gateway kwargs (pin, totp_secret, etc.).
    """

    def __init__(
        self,
        client_id: str | None = None,
        access_token: str | None = None,
        **kwargs: Any,
    ) -> None:
        self._client_id = client_id
        self._access_token = access_token
        self._gateway_kwargs = kwargs
        self._gw: Any = None

    @property
    def broker_id(self) -> str:
        return "dhan"

    @property
    def max_levels(self) -> int:
        return 200

    @property
    def is_connected(self) -> bool:
        if self._gw is None:
            return False
        streaming = getattr(self._gw, "streaming", None)
        if streaming is not None:
            return streaming.is_connected
        return True

    def connect(self, **credentials: Any) -> None:
        """Create and configure the DhanGateway."""
        from brokers.adapters.dhan.gateway import DhanGateway

        cid = credentials.get("client_id", self._client_id)
        token = credentials.get("access_token", self._access_token)

        self._gw = DhanGateway(
            client_id=cid,
            access_token=token,
            **self._gateway_kwargs,
        )
        logger.info("DhanAdapter connected (client_id=%s)", cid)

    def disconnect(self) -> None:
        """Close the gateway and release resources."""
        if self._gw is not None:
            self._gw.close()
            self._gw = None
            logger.info("DhanAdapter disconnected")

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
        """Get market depth with up to 200 levels.

        The ``levels`` parameter is accepted for API compatibility but the
        underlying Dhan gateway resolves the actual level count based on
        the subscription type (depth 20 vs depth 200).
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
        return self._gw.historical.get_candles(symbol, exchange, start, end, resolution)

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
        from inc_trade.domain.enums import OrderType, ProductType, Side, Validity

        side_enum = Side.BUY if side.upper() == "BUY" else Side.SELL
        ot = order_type or OrderType.MARKET
        return self._gw.orders.place_order(
            symbol=symbol,
            exchange=exchange,
            side=side_enum,
            quantity=quantity,
            order_type=ot,
            price=price,
            trigger_price=trigger_price,
            product_type=kwargs.get("product_type", ProductType.INTRADAY),
            validity=kwargs.get("validity", Validity.DAY),
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

        Automatically applies ``apply_depth=200`` for Dhan's max depth
        capability unless explicitly overridden.
        """
        if "apply_depth" not in kwargs:
            kwargs["apply_depth"] = 200
        return super().instrument(symbol, exchange, **kwargs)

    # ── Internals ─────────────────────────────────────────────────────

    def _require_gateway(self) -> None:
        if self._gw is None:
            raise RuntimeError("DhanAdapter not connected. Call adapter.connect() first.")
