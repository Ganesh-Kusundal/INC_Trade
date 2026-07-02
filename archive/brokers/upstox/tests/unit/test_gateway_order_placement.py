"""Tests for refactored UpstoxBrokerGateway order placement and instrument resolution.

These tests verify the critical security guards and resolution logic that were
moved from deleted hollow shims (OrderAdapter, SymbolResolverAdapter) into the gateway.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from domain import ExchangeSegment, OrderResponse


class TestGatewayAllowLiveOrdersGuard:
    """Critical security test: verify live orders can be disabled."""

    def test_place_order_blocked_when_live_orders_disabled(self):
        """Security guard: place_order must fail when allow_live_orders=False."""
        from brokers.upstox.gateway import UpstoxBrokerGateway

        mock_broker = MagicMock()
        mock_broker.settings.allow_live_orders = False
        mock_broker.settings.analytics_only = False
        mock_broker.order_command = MagicMock()
        mock_broker.instrument_resolver = MagicMock()

        gateway = UpstoxBrokerGateway(mock_broker)

        response = gateway.place_order("RELIANCE", "NSE", "BUY", 10)

        assert not response.success
        assert "Live orders are disabled" in response.message
        # Verify order_command was NEVER called
        mock_broker.order_command.place_order.assert_not_called()

    def test_cancel_order_blocked_when_live_orders_disabled(self):
        """Security guard: cancel_order checks allow_live_orders in order_command adapter."""
        from brokers.upstox.gateway import UpstoxBrokerGateway

        mock_broker = MagicMock()
        mock_broker.settings.allow_live_orders = True
        mock_broker.settings.analytics_only = False  # Gateway allows, but adapter checks
        mock_broker.instrument_resolver = MagicMock()

        # Mock order_command to simulate the allow_live_orders check
        mock_broker.order_command.cancel_order.return_value = OrderResponse.fail(
            "Live order cancellation is disabled. Set allow_live_orders=True in configuration."
        )

        gateway = UpstoxBrokerGateway(mock_broker)

        response = gateway.cancel_order("ORD123")

        assert not response.success
        assert "Live order cancellation is disabled" in response.message


class TestGatewayOrderPlacement:
    """Test the refactored order placement flow."""

    def test_place_order_success_logs_and_returns_response(self):
        """Verify successful order placement logs and returns response."""
        from brokers.upstox.gateway import UpstoxBrokerGateway

        mock_broker = MagicMock()
        mock_broker.settings.allow_live_orders = True
        mock_broker.settings.analytics_only = False
        mock_broker.instrument_resolver = MagicMock()

        mock_response = OrderResponse.ok(
            order_id="ORD123",
            message="Order placed",
        )
        mock_broker.order_command.place_order.return_value = mock_response

        gateway = UpstoxBrokerGateway(mock_broker)

        with patch("brokers.upstox.gateway.logger") as mock_logger:
            response = gateway.place_order(
                symbol="RELIANCE",
                exchange="NSE",
                side="BUY",
                quantity=10,
                price=Decimal("2500"),
                order_type="LIMIT",
                correlation_id="test-corr-123",
            )

        assert response.success
        assert response.order_id == "ORD123"
        mock_broker.order_command.place_order.assert_called_once()
        # Verify success logging
        mock_logger.info.assert_any_call(
            "order_placed",
            extra={
                "correlation_id": "test-corr-123",
                "order_id": "ORD123",
                "symbol": "RELIANCE",
                "side": "BUY",
            },
        )

    def test_place_order_passes_upstox_metadata_through_provider_metadata(self):
        from brokers.upstox.gateway import UpstoxBrokerGateway

        mock_broker = MagicMock()
        mock_broker.settings.allow_live_orders = True
        mock_broker.settings.analytics_only = False
        mock_broker.instrument_resolver = MagicMock()
        mock_broker.order_command.place_order.return_value = OrderResponse.ok(order_id="ORD123")

        gateway = UpstoxBrokerGateway(mock_broker)

        gateway.place_order(
            symbol="RELIANCE",
            exchange="NSE",
            side="BUY",
            quantity=10,
            is_amo=True,
        )

        request = mock_broker.order_command.place_order.call_args.args[0]
        assert request.provider_metadata["is_amo"] is True

    def test_place_order_failure_logs_warning(self):
        """Verify failed order placement logs warning."""
        from brokers.upstox.gateway import UpstoxBrokerGateway

        mock_broker = MagicMock()
        mock_broker.settings.allow_live_orders = True
        mock_broker.settings.analytics_only = False
        mock_broker.instrument_resolver = MagicMock()

        mock_response = OrderResponse.fail("Risk check failed: exposure limit exceeded")
        mock_broker.order_command.place_order.return_value = mock_response

        gateway = UpstoxBrokerGateway(mock_broker)

        with patch("brokers.upstox.gateway.logger") as mock_logger:
            response = gateway.place_order(
                symbol="RELIANCE",
                exchange="NSE",
                side="BUY",
                quantity=1000,
                correlation_id="test-corr-456",
            )

        assert not response.success
        assert "Risk check failed" in response.message
        # Verify failure logging
        mock_logger.warning.assert_any_call(
            "order_placement_rejected",
            extra={
                "correlation_id": "test-corr-456",
                "symbol": "RELIANCE",
                "side": "BUY",
                "error": "Risk check failed: exposure limit exceeded",
            },
        )

    def test_place_order_exception_logs_and_returns_fail(self):
        """Verify exception during placement is caught, logged, and returned as fail."""
        from brokers.upstox.gateway import UpstoxBrokerGateway

        mock_broker = MagicMock()
        mock_broker.settings.allow_live_orders = True
        mock_broker.settings.analytics_only = False
        mock_broker.instrument_resolver = MagicMock()
        mock_broker.order_command.place_order.side_effect = Exception("Network timeout")

        gateway = UpstoxBrokerGateway(mock_broker)

        with patch("brokers.upstox.gateway.logger") as mock_logger:
            response = gateway.place_order(
                symbol="RELIANCE",
                exchange="NSE",
                side="BUY",
                quantity=10,
            )

        assert not response.success
        assert "Network timeout" in response.message
        mock_logger.warning.assert_called_once_with(
            "order_placement_failed",
            extra={
                "correlation_id": None,
                "symbol": "RELIANCE",
                "side": "BUY",
                "error": "Network timeout",
            },
        )


class TestResolveInstrumentKey:
    """Test the instrument key resolution logic moved from SymbolResolverAdapter."""

    def test_index_symbol_resolves_to_nse_index(self):
        """Index symbols (NIFTY) should resolve to NSE_INDEX segment."""
        from brokers.upstox.gateway import UpstoxBrokerGateway
        from brokers.upstox.instruments.definition import UpstoxInstrumentDefinition
        from brokers.upstox.instruments.resolver import UpstoxInstrumentResolver
        from domain.market_enums import ExchangeSegment

        mock_broker = MagicMock()
        mock_broker.settings.allow_live_orders = True
        mock_broker.settings.analytics_only = False
        mock_broker.instrument_resolver = UpstoxInstrumentResolver()

        # Load index instrument
        index_def = UpstoxInstrumentDefinition(
            instrument_key="NSE_INDEX|Nifty 50",
            exchange_segment=ExchangeSegment.IDX_I,
            symbol="NIFTY",
            name="Nifty 50",
            instrument_type="INDEX",
            tick_size=0.05,
            lot_size=1,
        )
        mock_broker.instrument_resolver.register(index_def)

        gateway = UpstoxBrokerGateway(mock_broker)
        key = gateway._resolve_instrument_key("NIFTY", "NSE")

        assert "NSE_INDEX" in key
        assert "Nifty 50" in key

    def test_equity_symbol_resolves_to_isin(self):
        """Equity symbols should resolve to NSE_EQ|ISIN format."""
        from brokers.upstox.gateway import UpstoxBrokerGateway
        from brokers.upstox.instruments.definition import UpstoxInstrumentDefinition
        from brokers.upstox.instruments.resolver import UpstoxInstrumentResolver
        from domain.market_enums import ExchangeSegment

        mock_broker = MagicMock()
        mock_broker.settings.allow_live_orders = True
        mock_broker.settings.analytics_only = False
        mock_broker.instrument_resolver = UpstoxInstrumentResolver()

        # Load equity instrument
        equity_def = UpstoxInstrumentDefinition(
            instrument_key="NSE_EQ|INE002A01018",
            exchange_segment=ExchangeSegment.NSE,
            symbol="RELIANCE",
            name="Reliance Industries Ltd",
            instrument_type="EQUITY",
            tick_size=0.05,
            lot_size=1,
        )
        mock_broker.instrument_resolver.register(equity_def)

        gateway = UpstoxBrokerGateway(mock_broker)
        key = gateway._resolve_instrument_key("RELIANCE", "NSE")

        assert key == "NSE_EQ|INE002A01018"

    def test_unknown_symbol_falls_back_to_constructed_key(self):
        """Unknown symbols should fall back to segment|symbol construction."""
        from brokers.upstox.gateway import UpstoxBrokerGateway

        mock_broker = MagicMock()
        mock_broker.settings.allow_live_orders = True
        mock_broker.settings.analytics_only = False
        mock_broker.instrument_resolver = MagicMock()
        mock_broker.instrument_resolver.resolve.return_value = None

        gateway = UpstoxBrokerGateway(mock_broker)
        key = gateway._resolve_instrument_key("UNKNOWN", "NSE")

        assert key == "NSE_EQ|UNKNOWN"


class TestResolveExchangeSegment:
    """Test the exchange segment resolution logic."""

    def test_index_symbol_forces_idx_i_segment(self):
        """Index symbols should force IDX_I segment regardless of exchange."""
        from brokers.upstox.gateway import UpstoxBrokerGateway

        mock_broker = MagicMock()
        mock_broker.settings.allow_live_orders = True
        mock_broker.settings.analytics_only = False
        mock_broker.instrument_resolver = MagicMock()

        gateway = UpstoxBrokerGateway(mock_broker)

        # Patch at the indices module level
        with patch("config.indices.index_upstox_key", return_value="NSE_INDEX|Nifty 50"):
            result = gateway._resolve_exchange_segment("NSE", "NIFTY")

        assert result == ExchangeSegment.IDX_I

    def test_normal_exchange_parses_correctly(self):
        """Normal exchanges should parse to their canonical segments."""
        from brokers.upstox.gateway import UpstoxBrokerGateway

        mock_broker = MagicMock()
        mock_broker.settings.allow_live_orders = True
        mock_broker.settings.analytics_only = False
        mock_broker.instrument_resolver = MagicMock()

        gateway = UpstoxBrokerGateway(mock_broker)

        result = gateway._resolve_exchange_segment("NFO", "NIFTY26JUN26C25000")
        assert result == ExchangeSegment.NSE_FNO

    def test_unknown_segment_raises_value_error(self):
        """Unknown segments should raise ValueError."""
        from brokers.upstox.gateway import UpstoxBrokerGateway

        mock_broker = MagicMock()
        mock_broker.settings.allow_live_orders = True
        mock_broker.settings.analytics_only = False
        mock_broker.instrument_resolver = MagicMock()

        gateway = UpstoxBrokerGateway(mock_broker)

        with pytest.raises(ValueError, match="Unknown exchange segment"):
            gateway._resolve_exchange_segment("INVALID", "RELIANCE")


class TestModifyOrder:
    """Test the modify_order flow."""

    def test_modify_order_success(self):
        """Successful modification should return OrderResponse.ok."""
        from brokers.upstox.gateway import UpstoxBrokerGateway

        mock_broker = MagicMock()
        mock_broker.settings.allow_live_orders = True
        mock_broker.settings.analytics_only = False
        mock_broker.instrument_resolver = MagicMock()
        mock_broker.order_command.modify_order.return_value = {"status": "success"}

        gateway = UpstoxBrokerGateway(mock_broker)

        response = gateway.modify_order("ORD123", price=Decimal("2600"))

        assert response.success
        assert response.order_id == "ORD123"
        assert "modified" in response.message.lower()

    def test_modify_order_failure(self):
        """Failed modification should return OrderResponse.fail."""
        from brokers.upstox.gateway import UpstoxBrokerGateway

        mock_broker = MagicMock()
        mock_broker.settings.allow_live_orders = True
        mock_broker.settings.analytics_only = False
        mock_broker.instrument_resolver = MagicMock()
        mock_broker.order_command.modify_order.return_value = {
            "status": "failed",
            "message": "Order not found",
        }

        gateway = UpstoxBrokerGateway(mock_broker)

        response = gateway.modify_order("ORD999", price=Decimal("2600"))

        assert not response.success
        assert "Order not found" in response.message

    def test_modify_order_exception_handling(self):
        """Exception during modification should return OrderResponse.fail."""
        from brokers.upstox.gateway import UpstoxBrokerGateway

        mock_broker = MagicMock()
        mock_broker.settings.allow_live_orders = True
        mock_broker.settings.analytics_only = False
        mock_broker.instrument_resolver = MagicMock()
        mock_broker.order_command.modify_order.side_effect = Exception("API error")

        gateway = UpstoxBrokerGateway(mock_broker)

        response = gateway.modify_order("ORD123", price=Decimal("2600"))

        assert not response.success
        assert "API error" in response.message
