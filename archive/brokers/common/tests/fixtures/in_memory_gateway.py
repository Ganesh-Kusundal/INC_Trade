"""In-memory CommonBrokerGateway implementations for integration tests.

These are concrete adapter implementations (not unittest.mock) used to exercise
registry, router, coordinator, and stream orchestrator with real components.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date, datetime, timezone
from decimal import Decimal

from brokers.common.broker_port import (
    BrokerHealthSnapshot,
    BrokerStreamHandle,
    BrokerStreamPlan,
    HistoricalBarRequest,
    QuotaToken,
)
from brokers.common.capabilities import BrokerCapabilities, CapabilityDescriptor
from domain.entities import Balance, Order, OrderResponse, Position, Quote, Trade
from domain.entities.market import MarketDepth
from domain.historical import HistoricalBar, InstrumentRef
from domain.provenance import DataProvenance
from domain.requests import ModifyOrderRequest, OrderRequest


def _bar(
    instrument: InstrumentRef,
    timeframe: str,
    event_time: datetime,
    close: Decimal,
    broker_id: str,
    request_id: str,
) -> HistoricalBar:
    return HistoricalBar(
        instrument=instrument,
        timeframe=timeframe,
        event_time=event_time,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=100,
        provenance=DataProvenance.now(broker_id=broker_id, request_id=request_id),
    )


class InMemoryStreamHandle:
    """Minimal stream handle for orchestrator integration tests."""

    def __init__(self, broker_id: str, session_id: str | None = None) -> None:
        self._broker_id = broker_id
        self._session_id = session_id or f"session-{broker_id}"
        self._connected = True

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def broker_id(self) -> str:
        return self._broker_id

    async def disconnect(self) -> None:
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected


class InMemoryBrokerGateway:
    """Configurable in-memory gateway implementing CommonBrokerGateway."""

    def __init__(
        self,
        broker_id: str,
        capabilities: BrokerCapabilities,
        *,
        extensions: frozenset[str] = frozenset(),
        historical_fn: Callable[[HistoricalBarRequest, QuotaToken], Sequence[HistoricalBar]]
        | None = None,
        fail_historical: bool = False,
        alive: bool = True,
    ) -> None:
        self._broker_id = broker_id
        self._capabilities = capabilities
        self._extensions = extensions
        self._historical_fn = historical_fn
        self._fail_historical = fail_historical
        self._alive = alive
        self.historical_calls: list[HistoricalBarRequest] = []

    @property
    def broker_id(self) -> str:
        return self._broker_id

    def list_capabilities(self) -> CapabilityDescriptor:
        return CapabilityDescriptor.build(self._capabilities, self._extensions)

    def supports(self, feature: str) -> bool:
        return self._capabilities.supports(feature)

    async def place_order(self, request: OrderRequest, *, quota: QuotaToken) -> OrderResponse:
        return OrderResponse.ok(order_id="test-order-1")

    async def cancel_order(self, order_id: str, *, quota: QuotaToken) -> OrderResponse:
        return OrderResponse.ok(order_id=order_id, message="cancelled")

    async def modify_order(
        self, request: ModifyOrderRequest, *, quota: QuotaToken
    ) -> OrderResponse:
        return OrderResponse.ok(order_id=request.order_id)

    async def get_positions(self, *, quota: QuotaToken) -> list[Position]:
        return []

    async def get_margins(self, *, quota: QuotaToken) -> Balance:
        return Balance(available_balance=Decimal("100000"))

    async def get_orders(self, *, quota: QuotaToken) -> list[Order]:
        return []

    async def get_trades(self, *, quota: QuotaToken) -> list[Trade]:
        return []

    async def get_quote_snapshot(self, instrument: InstrumentRef, *, quota: QuotaToken) -> Quote:
        return Quote(symbol=instrument.symbol, ltp=Decimal("100"))

    async def get_depth_snapshot(
        self, instrument: InstrumentRef, *, quota: QuotaToken
    ) -> MarketDepth:
        return MarketDepth(symbol=instrument.symbol)

    async def get_historical_bars(
        self, request: HistoricalBarRequest, *, quota: QuotaToken
    ) -> Sequence[HistoricalBar]:
        self.historical_calls.append(request)
        if self._fail_historical:
            raise RuntimeError(f"historical fetch failed on {self._broker_id}")
        if self._historical_fn is not None:
            return self._historical_fn(request, quota)
        from_d = date.fromisoformat(request.from_date)
        return [
            _bar(
                request.instrument,
                request.timeframe,
                datetime(from_d.year, from_d.month, from_d.day, 9, 15, tzinfo=timezone.utc),
                Decimal("100.00"),
                self._broker_id,
                request.request_id,
            )
        ]

    async def open_market_stream(self, plan: BrokerStreamPlan) -> BrokerStreamHandle:
        return InMemoryStreamHandle(self._broker_id)

    async def open_order_stream(self, plan: BrokerStreamPlan) -> BrokerStreamHandle:
        return InMemoryStreamHandle(self._broker_id)

    async def health(self) -> BrokerHealthSnapshot:
        return BrokerHealthSnapshot(
            broker_id=self._broker_id,
            alive=self._alive,
            auth_valid=self._alive,
        )

    async def close(self) -> None:
        self._alive = False
