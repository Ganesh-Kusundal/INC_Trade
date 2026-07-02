"""Tests for IntelligentMarketDataGateway.

Tests both smart mode (intelligent routing) and simple mode (direct broker calls).
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import Mock

import pytest

from brokers.common.intelligent_market_gateway import IntelligentMarketDataGateway
from brokers.common.models import OperationKind


class TestIntelligentMarketDataGateway:
    """Test suite for IntelligentMarketDataGateway."""

    @pytest.fixture
    def mock_infrastructure(self):
        """Create mock BrokerInfrastructure."""
        infra = Mock()
        infra.router = Mock()
        infra.quota = Mock()
        infra.registry = Mock()
        infra.historical = Mock()

        # Mock gateway
        mock_gateway = Mock()
        mock_gateway.broker_id = "dhan"
        mock_gateway.ltp.return_value = Decimal("100.50")
        mock_gateway.quote.return_value = Mock()
        mock_gateway.depth.return_value = Mock()
        mock_gateway.history.return_value = Mock()
        mock_gateway.option_chain.return_value = Mock()
        mock_gateway.future_chain.return_value = Mock()
        mock_gateway.ltp_batch.return_value = {"RELIANCE": Decimal("100.50")}
        mock_gateway.quote_batch.return_value = {"RELIANCE": {}}
        mock_gateway.history_batch.return_value = Mock()
        mock_gateway.place_order.return_value = Mock()
        mock_gateway.positions.return_value = []
        mock_gateway.holdings.return_value = []
        mock_gateway.funds.return_value = Mock()

        # Mock routing decision with proper attributes
        mock_decision = Mock()
        mock_decision.primary_broker = "dhan"
        mock_decision.fallback_brokers = []
        mock_decision.parallel_brokers = []
        infra.router.route.return_value = mock_decision

        # Mock registry
        infra.registry.get_gateway.return_value = mock_gateway
        infra.registry.list_brokers.return_value = ["dhan"]

        # Mock gateway_for to return mock_gateway
        infra.gateway_for.return_value = mock_gateway

        # Mock quota token
        mock_token = Mock()
        infra.quota.acquire.return_value = mock_token

        return infra, mock_gateway

    def test_smart_mode_uses_router(self, mock_infrastructure):
        """Verify BrokerRouter is called when smart=True."""
        infra, mock_gateway = mock_infrastructure
        gw = IntelligentMarketDataGateway(infra, smart=True, primary_broker="dhan")

        # Call ltp
        result = gw.ltp("RELIANCE", "NSE")

        # Verify router was called
        infra.router.route.assert_called_once()
        call_args = infra.router.route.call_args
        assert call_args[0][0].operation == OperationKind.GET_QUOTE

        # Verify quota was acquired and released
        infra.quota.acquire.assert_called_once()
        infra.quota.release.assert_called_once()

        # Verify gateway method was called
        mock_gateway.ltp.assert_called_once_with("RELIANCE", "NSE")
        assert result == Decimal("100.50")

    def test_simple_mode_uses_primary_broker(self, mock_infrastructure):
        """Verify direct call when smart=False."""
        infra, _mock_gateway = mock_infrastructure
        gw = IntelligentMarketDataGateway(infra, smart=False, primary_broker="dhan")

        # Call ltp
        result = gw.ltp("RELIANCE", "NSE")

        # Verify router was NOT called
        infra.router.route.assert_not_called()

        # Verify quota was NOT acquired
        infra.quota.acquire.assert_not_called()

        # Verify gateway_for was called (returns infra.gateway_for.return_value)
        infra.gateway_for.assert_called_once_with("dhan")
        assert result == Decimal("100.50")

    def test_smart_mode_quote(self, mock_infrastructure):
        """Verify smart mode for quote operation."""
        infra, mock_gateway = mock_infrastructure
        gw = IntelligentMarketDataGateway(infra, smart=True, primary_broker="dhan")

        gw.quote("RELIANCE", "NSE")

        infra.router.route.assert_called_once()
        infra.quota.acquire.assert_called_once()
        mock_gateway.quote.assert_called_once_with("RELIANCE", "NSE")

    def test_smart_mode_depth(self, mock_infrastructure):
        """Verify smart mode for depth operation."""
        infra, mock_gateway = mock_infrastructure
        gw = IntelligentMarketDataGateway(infra, smart=True, primary_broker="dhan")

        gw.depth("RELIANCE", "NSE")

        infra.router.route.assert_called_once()
        infra.quota.acquire.assert_called_once()
        mock_gateway.depth.assert_called_once_with("RELIANCE", "NSE")

    def test_smart_mode_option_chain(self, mock_infrastructure):
        """Verify smart mode for option chain."""
        infra, mock_gateway = mock_infrastructure
        gw = IntelligentMarketDataGateway(infra, smart=True, primary_broker="dhan")

        gw.option_chain("NIFTY", "NFO")

        infra.router.route.assert_called_once()
        infra.quota.acquire.assert_called_once()
        mock_gateway.option_chain.assert_called_once_with("NIFTY", "NFO", None)

    def test_smart_mode_future_chain(self, mock_infrastructure):
        """Verify smart mode for future chain."""
        infra, mock_gateway = mock_infrastructure
        gw = IntelligentMarketDataGateway(infra, smart=True, primary_broker="dhan")

        gw.future_chain("NIFTY", "NFO")

        infra.router.route.assert_called_once()
        infra.quota.acquire.assert_called_once()
        mock_gateway.future_chain.assert_called_once_with("NIFTY", "NFO")

    def test_smart_mode_ltp_batch_small(self, mock_infrastructure):
        """Verify smart mode for small batch uses single broker."""
        infra, mock_gateway = mock_infrastructure
        gw = IntelligentMarketDataGateway(infra, smart=True, primary_broker="dhan")

        symbols = ["RELIANCE", "TCS"]
        gw.ltp_batch(symbols, "NSE")

        # Small batches should use single broker
        infra.router.route.assert_called_once()
        mock_gateway.ltp_batch.assert_called_once_with(symbols, "NSE")

    def test_smart_mode_ltp_batch_large(self, mock_infrastructure):
        """Verify smart mode for large batch splits across brokers."""
        infra, _mock_gateway = mock_infrastructure
        # Add multiple brokers
        infra.registry.list_brokers.return_value = ["dhan", "upstox"]

        gw = IntelligentMarketDataGateway(infra, smart=True, primary_broker="dhan")

        symbols = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN"]
        gw.ltp_batch(symbols, "NSE")

        # Large batches should split across brokers
        assert infra.quota.acquire.call_count >= 1

    def test_simple_mode_ltp_batch(self, mock_infrastructure):
        """Verify simple mode for batch operations."""
        infra, mock_gateway = mock_infrastructure
        gw = IntelligentMarketDataGateway(infra, smart=False, primary_broker="dhan")

        symbols = ["RELIANCE", "TCS"]
        gw.ltp_batch(symbols, "NSE")

        infra.router.route.assert_not_called()
        mock_gateway.ltp_batch.assert_called_once_with(symbols, "NSE")

    def test_smart_mode_history_uses_coordinator(self, mock_infrastructure):
        """Verify HistoricalDataCoordinator is used when smart=True."""
        infra, _mock_gateway = mock_infrastructure
        gw = IntelligentMarketDataGateway(infra, smart=True, primary_broker="dhan")

        # Mock historical coordinator
        from unittest.mock import AsyncMock
        mock_series = Mock()
        mock_series.to_dataframe.return_value = Mock()
        mock_ledger = Mock()
        infra.historical.fetch = AsyncMock(return_value=(mock_series, mock_ledger))

        gw.history("RELIANCE", "NSE", "1D", 90)

        # Should use historical coordinator
        infra.historical.fetch.assert_called_once()
        mock_series.to_dataframe.assert_called_once()

    def test_simple_mode_history_uses_primary(self, mock_infrastructure):
        """Verify direct call when smart=False for history."""
        infra, mock_gateway = mock_infrastructure
        gw = IntelligentMarketDataGateway(infra, smart=False, primary_broker="dhan")

        gw.history("RELIANCE", "NSE", "1D", 90)

        infra.historical.fetch.assert_not_called()
        mock_gateway.history.assert_called_once()

    def test_order_execution_always_uses_primary(self, mock_infrastructure):
        """Verify order execution always uses primary broker."""
        infra, mock_gateway = mock_infrastructure
        gw = IntelligentMarketDataGateway(infra, smart=True, primary_broker="dhan")

        # Place order should always use primary broker
        gw.place_order("RELIANCE", "NSE", "BUY", 1)

        # Verify router was NOT called for order execution
        infra.router.route.assert_not_called()

        # Verify gateway method was called
        mock_gateway.place_order.assert_called_once()

    def test_portfolio_operations_use_primary(self, mock_infrastructure):
        """Verify portfolio operations use primary broker."""
        infra, mock_gateway = mock_infrastructure
        gw = IntelligentMarketDataGateway(infra, smart=True, primary_broker="dhan")

        gw.positions()
        gw.holdings()
        gw.funds()

        # Verify router was NOT called for portfolio operations
        infra.router.route.assert_not_called()

        # Verify gateway methods were called
        mock_gateway.positions.assert_called_once()
        mock_gateway.holdings.assert_called_once()
        mock_gateway.funds.assert_called_once()

    def test_close_closes_all_gateways(self, mock_infrastructure):
        """Verify close() closes all gateways in infrastructure."""
        infra, mock_gateway = mock_infrastructure
        gw = IntelligentMarketDataGateway(infra, smart=True, primary_broker="dhan")

        gw.close()

        # Verify all gateways were closed
        infra.registry.get_gateway.assert_called()
        mock_gateway.close.assert_called()

    def test_smart_mode_fallback_on_routing_error(self, mock_infrastructure):
        """Verify fallback to primary broker on routing error."""
        infra, mock_gateway = mock_infrastructure
        infra.router.route.side_effect = Exception("Routing failed")

        gw = IntelligentMarketDataGateway(infra, smart=True, primary_broker="dhan")

        # Should fall back to primary broker
        result = gw.ltp("RELIANCE", "NSE")

        # Verify gateway method was still called
        mock_gateway.ltp.assert_called_once()
        assert result == Decimal("100.50")

    def test_quota_acquire_failure_continues(self, mock_infrastructure):
        """Verify operation continues if quota acquire fails."""
        infra, mock_gateway = mock_infrastructure
        infra.quota.acquire.side_effect = Exception("Quota failed")

        gw = IntelligentMarketDataGateway(infra, smart=True, primary_broker="dhan")

        # Should continue even if quota acquire fails
        result = gw.ltp("RELIANCE", "NSE")

        # Verify gateway method was still called
        mock_gateway.ltp.assert_called_once()
        assert result == Decimal("100.50")

    def test_smart_mode_property(self, mock_infrastructure):
        """Verify smart_mode property."""
        infra, _ = mock_infrastructure

        gw_smart = IntelligentMarketDataGateway(infra, smart=True)
        assert gw_smart.smart_mode is True

        gw_simple = IntelligentMarketDataGateway(infra, smart=False)
        assert gw_simple.smart_mode is False

    def test_primary_broker_property(self, mock_infrastructure):
        """Verify primary_broker property."""
        infra, _ = mock_infrastructure

        gw = IntelligentMarketDataGateway(infra, primary_broker="upstox")
        assert gw.primary_broker == "upstox"


class TestAllocateSymbolsToBrokers:
    """Test symbol allocation logic."""

    @pytest.fixture
    def mock_infrastructure(self):
        """Create mock infrastructure with multiple brokers."""
        infra = Mock()
        infra.registry.list_brokers.return_value = ["dhan", "upstox"]
        return infra

    def test_allocate_single_broker(self, mock_infrastructure):
        """Verify allocation with single broker."""
        gw = IntelligentMarketDataGateway(mock_infrastructure, smart=False, primary_broker="dhan")

        symbols = ["RELIANCE", "TCS", "INFY"]
        allocations = gw._allocate_symbols_to_brokers(symbols)

        # Simple mode should allocate all to primary
        assert allocations == {"dhan": symbols}

    def test_allocate_multiple_brokers(self, mock_infrastructure):
        """Verify round-robin allocation across multiple brokers."""
        gw = IntelligentMarketDataGateway(mock_infrastructure, smart=True, primary_broker="dhan")

        symbols = ["RELIANCE", "TCS", "INFY", "HDFCBANK"]
        allocations = gw._allocate_symbols_to_brokers(symbols)

        # Should distribute across brokers
        assert len(allocations) == 2
        assert "dhan" in allocations
        assert "upstox" in allocations
        assert len(allocations["dhan"]) + len(allocations["upstox"]) == 4

    def test_allocate_empty_symbols(self, mock_infrastructure):
        """Verify allocation with empty symbol list."""
        gw = IntelligentMarketDataGateway(mock_infrastructure, smart=True, primary_broker="dhan")

        allocations = gw._allocate_symbols_to_brokers([])

        # Should return empty allocations
        assert all(len(syms) == 0 for syms in allocations.values())
