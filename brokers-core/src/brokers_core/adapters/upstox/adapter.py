"""UpstoxAdapter — directly composes Upstox sub-adapters without UpstoxGateway.

Usage::

    from brokers_core.adapters.upstox import UpstoxAdapter

    adapter = UpstoxAdapter(access_token="abc")
    adapter.connect()

    inst = adapter.instrument("RELIANCE", "NSE", apply_depth=30)
    inst.quote()
    inst.depth(30)
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from brokers_core.adapters.base import ConnectedGuard
from brokers_core.adapters.upstox.composition import (
    UpstoxComponents,
    build_upstox_components,
    teardown_upstox_components,
)
from brokers_core.domain.constants.broker_ids import UPSTOX_ID
from brokers_core.domain.enums import Side

if TYPE_CHECKING:
    from brokers_core.domain.entities import Candle, MarketDepth, OptionChain, Quote

logger = logging.getLogger(__name__)


class UpstoxAdapter(ConnectedGuard):
    """Upstox broker adapter — implements provider protocols directly.

    Composes Upstox sub-adapters without using the UpstoxGateway facade.

    Args:
        access_token: Upstox API access token.
        allow_live_orders: Enable live order placement.
        auto_refresh: Enable TOTP refresh scheduler when configured.
        load_instruments: Load instrument master on connect.
        **kwargs: Forwarded to ``build_upstox_components`` (settings, lifecycle).
    """

    def __init__(
        self,
        access_token: str | None = None,
        allow_live_orders: bool | None = None,
        auto_refresh: bool = True,
        load_instruments: bool = False,
        **kwargs: Any,
    ) -> None:
        self._access_token = access_token
        self._allow_live_orders = allow_live_orders
        self._auto_refresh = auto_refresh
        self._load_instruments = load_instruments
        self._connect_kwargs = kwargs
        self._components: UpstoxComponents | None = None

    @property
    def broker_id(self) -> str:
        return UPSTOX_ID

    @property
    def max_levels(self) -> int:
        return 30

    @property
    def is_connected(self) -> bool:
        if not self._connected or self._components is None:
            return False
        streaming = self._components.streaming
        if streaming is not None:
            return streaming.is_connected
        return True

    def connect(self, **credentials: Any) -> None:
        """Authenticate and wire all Upstox sub-adapters."""
        token = credentials.get("access_token", self._access_token)
        self._components = build_upstox_components(
            access_token=token,
            allow_live_orders=self._allow_live_orders,
            auto_refresh=self._auto_refresh,
            load_instruments=self._load_instruments,
            **self._connect_kwargs,
        )
        self._connected = True
        logger.info("UpstoxAdapter connected")

    def disconnect(self) -> None:
        """Close streaming, scheduler, and HTTP client."""
        if self._components is not None:
            teardown_upstox_components(self._components)
            self._components = None
        self._connected = False
        logger.info("UpstoxAdapter disconnected")

    # ── InstrumentDataProvider ────────────────────────────────────────

    def quote(self, symbol: str, exchange: str = "NSE") -> Quote:
        self._require_connected()
        return self._components.market_data.quote(symbol, exchange)

    def ltp(self, symbol: str, exchange: str = "NSE") -> Decimal:
        self._require_connected()
        return self._components.market_data.ltp(symbol, exchange)

    def quote_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Quote]:
        self._require_connected()
        return self._components.market_data.quote_batch(symbols, exchange)

    def depth(self, symbol: str, exchange: str = "NSE", levels: int = 5) -> MarketDepth:
        self._require_connected()
        return self._components.market_data.depth(symbol, exchange)

    def get_option_chain(
        self,
        underlying: str,
        exchange: str = "NFO",
        expiry: str | None = None,
    ) -> OptionChain:
        self._require_connected()
        return self._components.options.get_option_chain(underlying, exchange, expiry)

    # ── HistoricalDataProvider ────────────────────────────────────────

    def get_candles(
        self,
        symbol: str,
        exchange: str,
        start: datetime,
        end: datetime,
        resolution: str,
    ) -> list[Candle]:
        self._require_connected()
        return self._components.historical.get_historical_candles(
            symbol,
            exchange,
            start,
            end,
            resolution,
        )

    # ── StreamingDataProvider ─────────────────────────────────────────

    def subscribe(self, instrument: Any, callback: Any) -> Any:
        self._require_connected()
        return self._components.streaming.subscribe(instrument, callback)

    def unsubscribe(self, instrument: Any) -> None:
        self._require_connected()
        self._components.streaming.unsubscribe(instrument)

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
    ) -> Any:
        self.require_connected()
        return self._components.orders.place_order(
            symbol=symbol,
            exchange=exchange,
            side=side,
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
        self._require_connected()
        return self._components.orders.modify_order(
            order_id=order_id,
            quantity=quantity,
            price=price,
        )

    def cancel_order(self, order_id: str) -> Any:
        self._require_connected()
        return self._components.orders.cancel_order(order_id)

    def instrument(self, symbol: str, exchange: str, **kwargs: Any) -> Any:
        """Create an Instrument with this adapter injected as provider."""
        from brokers_core.market.factory import InstrumentFactory

        if "apply_depth" not in kwargs:
            kwargs["apply_depth"] = 30
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

    def _require_connected(self) -> None:
        self.require_connected()
        if self._components is None:
            raise RuntimeError("UpstoxAdapter not connected. Call adapter.connect() first.")

    def __repr__(self) -> str:
        status = "connected" if self._connected else "disconnected"
        return f"UpstoxAdapter(status={status})"
