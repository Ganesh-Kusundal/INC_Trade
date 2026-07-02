"""CommonBrokerGateway — contract tests verifying the async v2 protocol.

Subclasses must provide a ``gateway`` fixture returning an object that
satisfies :class:`~brokers.common.broker_port.CommonBrokerGateway`.
"""

from __future__ import annotations

from typing import Any

import pytest

from brokers.common.broker_port import (
    BrokerHealthSnapshot,
    BrokerStreamHandle,
    BrokerStreamPlan,
    CommonBrokerGateway,
    HistoricalBarRequest,
    QuotaToken,
)
from brokers.common.capabilities import CapabilityDescriptor
from domain.entities import Balance, Order, OrderResponse, Position, Quote, Trade
from domain.entities.market import MarketDepth
from domain.historical import HistoricalBar, InstrumentRef


class CommonBrokerGatewayContractSuite:
    """Contract tests for any CommonBrokerGateway implementation."""

    @pytest.fixture
    def gateway(self) -> CommonBrokerGateway:
        raise NotImplementedError(
            "gateway fixture must return a CommonBrokerGateway implementation"
        )

    @pytest.fixture
    def quota_token(self) -> QuotaToken:
        return QuotaToken(
            broker_id="test",
            endpoint_class="orders",
            priority_class="high",
            token_id="test-token",
        )

    # ── Protocol conformance ──────────────────────────────────────────────

    def test_gateway_satisfies_protocol(self, gateway: Any) -> None:
        assert isinstance(gateway, CommonBrokerGateway)

    def test_has_broker_id(self, gateway: Any) -> None:
        assert hasattr(gateway, "broker_id")
        assert isinstance(gateway.broker_id, str)
        assert len(gateway.broker_id) > 0

    # ── Capability discovery ──────────────────────────────────────────────

    def test_list_capabilities_returns_descriptor(self, gateway: Any) -> None:
        result = gateway.list_capabilities()
        assert isinstance(result, CapabilityDescriptor)

    def test_supports_returns_bool(self, gateway: Any) -> None:
        result = gateway.supports("place_order")
        assert isinstance(result, bool)

    # ── Order execution ──────────────────────────────────────────────────

    def test_place_order_returns_order_response(self, gateway: Any, quota_token: QuotaToken) -> None:
        from domain.requests import OrderRequest
        from domain.types import Side

        request = OrderRequest(
            symbol="RELIANCE",
            exchange="NSE",
            transaction_type=Side.BUY,
            quantity=1,
            order_type="MARKET",
        )
        result = gateway.place_order(request, quota=quota_token)
        assert isinstance(result, OrderResponse)

    def test_cancel_order_returns_order_response(self, gateway: Any, quota_token: QuotaToken) -> None:
        result = gateway.cancel_order("ORD-123", quota=quota_token)
        assert isinstance(result, OrderResponse)

    def test_modify_order_returns_order_response(self, gateway: Any, quota_token: QuotaToken) -> None:
        from domain.requests import ModifyOrderRequest

        request = ModifyOrderRequest(order_id="ORD-123", quantity=2)
        result = gateway.modify_order(request, quota=quota_token)
        assert isinstance(result, OrderResponse)

    # ── Portfolio reads ──────────────────────────────────────────────────

    def test_get_positions_returns_list(self, gateway: Any, quota_token: QuotaToken) -> None:
        result = gateway.get_positions(quota=quota_token)
        assert isinstance(result, list)

    def test_get_margins_returns_balance(self, gateway: Any, quota_token: QuotaToken) -> None:
        result = gateway.get_margins(quota=quota_token)
        assert isinstance(result, Balance)

    def test_get_orders_returns_list(self, gateway: Any, quota_token: QuotaToken) -> None:
        result = gateway.get_orders(quota=quota_token)
        assert isinstance(result, list)

    def test_get_trades_returns_list(self, gateway: Any, quota_token: QuotaToken) -> None:
        result = gateway.get_trades(quota=quota_token)
        assert isinstance(result, list)

    # ── Point-in-time market reads ───────────────────────────────────────

    def test_get_quote_snapshot_returns_quote(
        self, gateway: Any, quota_token: QuotaToken
    ) -> None:
        instrument = InstrumentRef(symbol="RELIANCE", exchange="NSE")
        result = gateway.get_quote_snapshot(instrument, quota=quota_token)
        assert isinstance(result, Quote)

    def test_get_depth_snapshot_returns_market_depth(
        self, gateway: Any, quota_token: QuotaToken
    ) -> None:
        instrument = InstrumentRef(symbol="RELIANCE", exchange="NSE")
        result = gateway.get_depth_snapshot(instrument, quota=quota_token)
        assert isinstance(result, MarketDepth)

    # ── Historical data ──────────────────────────────────────────────────

    def test_get_historical_bars_returns_sequence(
        self, gateway: Any, quota_token: QuotaToken
    ) -> None:
        request = HistoricalBarRequest(
            instrument=InstrumentRef(symbol="RELIANCE", exchange="NSE"),
            timeframe="1D",
            from_date="2024-01-01",
            to_date="2024-01-31",
            request_id="test-request",
        )
        result = gateway.get_historical_bars(request, quota=quota_token)
        assert hasattr(result, "__iter__")

    # ── Stream handle factories ──────────────────────────────────────────

    def test_open_market_stream_returns_handle(self, gateway: Any) -> None:
        plan = BrokerStreamPlan(
            instruments=frozenset({"NSE:RELIANCE"}),
            modes=frozenset({"LTP"}),
        )
        result = gateway.open_market_stream(plan)
        assert isinstance(result, BrokerStreamHandle)

    def test_open_order_stream_returns_handle(self, gateway: Any) -> None:
        plan = BrokerStreamPlan(
            instruments=frozenset(),
            modes=frozenset(),
        )
        result = gateway.open_order_stream(plan)
        assert isinstance(result, BrokerStreamHandle)

    # ── Lifecycle ────────────────────────────────────────────────────────

    def test_health_returns_snapshot(self, gateway: Any) -> None:
        result = gateway.health()
        assert isinstance(result, BrokerHealthSnapshot)

    def test_close_is_callable(self, gateway: Any) -> None:
        gateway.close()


class _MockCommonBrokerGateway:
    """Minimal stand-in for protocol conformance testing."""

    broker_id = "mock"

    def list_capabilities(self) -> CapabilityDescriptor:
        from brokers.common.capabilities import BrokerCapabilities

        return CapabilityDescriptor(
            broker_id="mock",
            capabilities=BrokerCapabilities(broker_id="mock"),
            extensions=frozenset(),
            observed_at=__import__("datetime").datetime.now(
                tz=__import__("datetime").timezone.utc
            ),
        )

    def supports(self, feature: str) -> bool:
        return True

    def place_order(self, request: Any, *, quota: QuotaToken) -> OrderResponse:
        return OrderResponse.ok(order_id="MOCK-1", message="ok")

    def cancel_order(self, order_id: str, *, quota: QuotaToken) -> OrderResponse:
        return OrderResponse.ok(order_id=order_id, message="cancelled")

    def modify_order(self, request: Any, *, quota: QuotaToken) -> OrderResponse:
        return OrderResponse.ok(order_id="MOCK-1", message="modified")

    def get_positions(self, *, quota: QuotaToken) -> list[Position]:
        return []

    def get_margins(self, *, quota: QuotaToken) -> Balance:
        return Balance(
            available_balance=0,
            used_margin=0,
            total_margin=0,
            sod_limit=0,
            collateral_amount=0,
            utilized_amount=0,
            withdrawable_balance=0,
        )

    def get_orders(self, *, quota: QuotaToken) -> list[Order]:
        return []

    def get_trades(self, *, quota: QuotaToken) -> list[Trade]:
        return []

    def get_quote_snapshot(
        self, instrument: InstrumentRef, *, quota: QuotaToken
    ) -> Quote:
        return Quote(
            symbol=instrument.symbol,
            ltp=0,
            open=0,
            high=0,
            low=0,
            close=0,
            volume=0,
            change=0,
            bid=0,
            ask=0,
            timestamp=None,
        )

    def get_depth_snapshot(
        self, instrument: InstrumentRef, *, quota: QuotaToken
    ) -> MarketDepth:
        return MarketDepth(symbol=instrument.symbol, bids=[], asks=[])

    def get_historical_bars(
        self, request: HistoricalBarRequest, *, quota: QuotaToken
    ) -> list[HistoricalBar]:
        return []

    def open_market_stream(self, plan: BrokerStreamPlan) -> BrokerStreamHandle:
        class _Handle(BrokerStreamHandle):
            session_id = "mock"
            broker_id = "mock"

            def disconnect(self) -> None:
                pass

            def is_connected(self) -> bool:
                return False

        return _Handle()

    def open_order_stream(self, plan: BrokerStreamPlan) -> BrokerStreamHandle:
        class _Handle(BrokerStreamHandle):
            session_id = "mock"
            broker_id = "mock"

            def disconnect(self) -> None:
                pass

            def is_connected(self) -> bool:
                return False

        return _Handle()

    def health(self) -> BrokerHealthSnapshot:
        return BrokerHealthSnapshot(broker_id="mock", alive=True)

    def close(self) -> None:
        pass


class TestCommonBrokerGatewayContract(CommonBrokerGatewayContractSuite):
    @pytest.fixture
    def gateway(self) -> CommonBrokerGateway:
        return _MockCommonBrokerGateway()

    @pytest.fixture
    def quota_token(self) -> QuotaToken:
        return QuotaToken(
            broker_id="mock",
            endpoint_class="orders",
            priority_class="high",
            token_id="mock-token",
        )
