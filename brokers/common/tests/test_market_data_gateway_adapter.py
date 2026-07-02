"""Integration tests for MarketDataGatewayAdapter using PaperGateway."""

from __future__ import annotations

from unittest import mock

import pytest

from brokers.common.adapters.market_data_gateway_adapter import (
    MarketDataGatewayAdapter,
    wrap_market_gateway,
)
from brokers.common.broker_port import BrokerStreamPlan, HistoricalBarRequest, QuotaToken
from brokers.common.capabilities import BrokerCapabilities
from brokers.dhan.capabilities import dhan_capabilities
from brokers.paper import PaperGateway
from domain.enums import OrderType, ProductType, Side, Validity
from domain.historical import InstrumentRef
from domain.requests import OrderRequest


@pytest.fixture
def paper_adapter():
    caps = BrokerCapabilities(
        broker_id="paper",
        supports_place_order=True,
        supports_cancel_order=True,
        supports_historical_data=True,
        supports_live_market_data=True,
    )
    return wrap_market_gateway(PaperGateway(), "paper", capabilities=caps)


class TestMarketDataGatewayAdapter:
    @pytest.mark.asyncio
    async def test_list_capabilities(self, paper_adapter):
        desc = paper_adapter.list_capabilities()
        assert desc.broker_id == "paper"
        assert desc.capabilities.supports_place_order

    @pytest.mark.asyncio
    async def test_get_quote_snapshot(self, paper_adapter):
        token = QuotaToken("paper", "quotes", "PORTFOLIO_READ", "t1")
        quote = await paper_adapter.get_quote_snapshot(
            InstrumentRef("RELIANCE", "NSE"), quota=token
        )
        assert quote.symbol == "RELIANCE"

    @pytest.mark.asyncio
    async def test_place_order_via_adapter(self, paper_adapter):
        token = QuotaToken("paper", "orders", "EXECUTION_CRITICAL", "t2")
        request = OrderRequest(
            symbol="RELIANCE",
            exchange="NSE",
            transaction_type=Side.BUY,
            quantity=1,
            order_type=OrderType.MARKET,
            product_type=ProductType.INTRADAY,
            validity=Validity.DAY,
        )
        response = await paper_adapter.place_order(request, quota=token)
        assert response.success

    @pytest.mark.asyncio
    async def test_get_historical_bars(self, paper_adapter):
        token = QuotaToken("paper", "historical", "HISTORICAL_BACKFILL", "t3")
        request = HistoricalBarRequest(
            instrument=InstrumentRef("RELIANCE", "NSE"),
            timeframe="1D",
            from_date="2025-01-01",
            to_date="2025-01-10",
            request_id="paper-hist-1",
        )
        bars = await paper_adapter.get_historical_bars(request, quota=token)
        assert isinstance(bars, list)

    @pytest.mark.asyncio
    async def test_health(self, paper_adapter):
        health = await paper_adapter.health()
        assert health.broker_id == "paper"
        assert health.alive

    def test_wrap_market_gateway_uses_legacy_gateway_capabilities_for_unknown_broker(self):
        legacy = mock.MagicMock()
        legacy.capabilities.return_value = BrokerCapabilities(
            broker_id="custom",
            supports_news=True,
        )

        adapter = wrap_market_gateway(legacy, "custom")

        assert adapter.list_capabilities().capabilities.supports("news")


class TestMarketDataGatewayAdapterOrderStream:
    @pytest.mark.asyncio
    async def test_open_order_stream_routes_through_broker_order_api(self):
        legacy = mock.MagicMock()
        legacy.stream_order.return_value = mock.MagicMock(is_connected=True)

        adapter = MarketDataGatewayAdapter(legacy, "dhan", capabilities=dhan_capabilities())
        plan = BrokerStreamPlan(instruments=frozenset(), modes=frozenset())

        await adapter.open_order_stream(plan)

        legacy.stream_order.assert_called_once()
        legacy.stream.assert_not_called()
