"""Tests for BrokerGateway — delegation to connection adapters."""

from __future__ import annotations

import os
import sys
from decimal import Decimal
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

from brokers.dhan.connection import DhanConnection
from brokers.dhan.domain import Order, OrderType, Position, Side
from brokers.dhan.gateway import BrokerGateway
from brokers.dhan.tests.conftest import FakeHttpClient
from domain import Balance, OrderRequest, Quote


class TestBrokerGateway:
    """Verify that BrokerGateway delegates every call to the correct adapter."""

    def _make_gateway(self) -> tuple[BrokerGateway, DhanConnection]:
        """Create a gateway backed by a FakeHttpClient and mocked adapters."""
        client = FakeHttpClient()
        conn = DhanConnection(client=client)

        # Replace each adapter with a MagicMock so we can assert calls
        conn._market_data = MagicMock()
        conn._orders = MagicMock()
        conn._portfolio = MagicMock()

        gateway = BrokerGateway(conn)
        return gateway, conn

    # -- market data delegation ------------------------------------------

    def test_get_quote_delegates(self):
        """gateway.get_quote must call market_data.get_quote with same args."""
        gateway, conn = self._make_gateway()

        expected = Quote(symbol="RELIANCE", ltp=Decimal("2500"))
        conn._market_data.get_quote.return_value = expected

        result = gateway.quote("RELIANCE", "NSE")

        conn._market_data.get_quote.assert_called_once_with("RELIANCE", "NSE")
        assert result is expected

    # -- portfolio delegation --------------------------------------------

    def test_get_balance_delegates(self):
        """gateway.funds() must call portfolio.get_balance."""
        gateway, conn = self._make_gateway()

        expected = Balance(available_balance=Decimal("50000"))
        conn._portfolio.get_balance.return_value = expected

        result = gateway.funds()

        conn._portfolio.get_balance.assert_called_once()
        assert result is expected

    def test_get_balance_canonical_delegates(self):
        """gateway.get_balance() must delegate to portfolio.get_balance."""
        gateway, conn = self._make_gateway()

        expected = Balance(
            available_balance=Decimal("500000"),
            sod_limit=Decimal("1000000"),
            collateral_amount=Decimal("200000"),
            utilized_amount=Decimal("300000"),
            withdrawable_balance=Decimal("400000"),
        )
        conn._portfolio.get_balance.return_value = expected

        result = gateway.get_balance()

        conn._portfolio.get_balance.assert_called_once()
        assert result is expected
        assert result.available_balance == Decimal("500000")
        assert result.sod_limit == Decimal("1000000")

    def test_funds_aliases_get_balance(self):
        """funds() and get_balance() must return the same result."""
        gateway, conn = self._make_gateway()

        expected = Balance(available_balance=Decimal("75000"))
        conn._portfolio.get_balance.return_value = expected

        assert gateway.funds() == gateway.get_balance()
        assert conn._portfolio.get_balance.call_count == 2

    def test_get_positions_delegates(self):
        """gateway.get_positions must call portfolio.get_positions."""
        gateway, conn = self._make_gateway()

        expected = [Position(symbol="RELIANCE", exchange="NSE", quantity=10)]
        conn._portfolio.get_positions.return_value = expected

        result = gateway.positions()

        conn._portfolio.get_positions.assert_called_once()
        assert result is expected

    # -- orders delegation -----------------------------------------------

    def test_place_order_delegates(self):
        """gateway.place_order must call orders.place_order with same kwargs."""
        gateway, conn = self._make_gateway()

        from domain import OrderResponse

        expected = Order(
            order_id="ORD-001",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            quantity=10,
        )
        conn._orders.place_order.return_value = expected

        result = gateway.place_order(
            symbol="RELIANCE",
            exchange="NSE",
            side="BUY",
            quantity=10,
        )

        call_args = conn._orders.place_order.call_args[0]
        assert len(call_args) == 1
        request = call_args[0]
        assert isinstance(request, OrderRequest)
        assert request.symbol == "RELIANCE"
        assert request.exchange == "NSE"
        assert request.transaction_type.value == "BUY"
        assert request.quantity == 10
        assert request.price is None or request.price == Decimal("0")
        assert request.order_type.value == "MARKET"
        assert request.trigger_price is None
        assert request.product_type.value == "INTRADAY"
        assert request.validity.value == "DAY"
        assert request.correlation_id is None
        assert isinstance(result, OrderResponse)
        assert result.success is True
        assert result.order_id == "ORD-001"

    def test_place_order_mcx_resolves_canonical_segment(self):
        """MCX exchange must map to ExchangeSegment.MCX, not silently fall back to NSE."""
        from domain import ExchangeSegment

        gateway, conn = self._make_gateway()
        conn._orders.place_order.return_value = Order(
            order_id="ORD-MCX",
            symbol="GOLD",
            exchange="MCX",
            side=Side.BUY,
            order_type=OrderType.MARKET,
            quantity=1,
        )

        gateway.place_order(symbol="GOLD", exchange="MCX", side="BUY", quantity=1)

        request = conn._orders.place_order.call_args[0][0]
        assert request.exchange_segment is ExchangeSegment.MCX

    def test_place_order_unknown_exchange_raises(self):
        gateway, _conn = self._make_gateway()
        import pytest

        with pytest.raises(ValueError, match="Unknown exchange"):
            gateway.place_order(symbol="X", exchange="BOGUS", quantity=1)

    # -- lifecycle -------------------------------------------------------

    def test_close_closes_client(self):
        """gateway.close() must propagate to the underlying HTTP client."""
        client = FakeHttpClient()
        conn = DhanConnection(client=client)
        # Replace the client's close with a mock to track the call
        client.close = MagicMock()
        gateway = BrokerGateway(conn)

        gateway.close()

        client.close.assert_called_once()
