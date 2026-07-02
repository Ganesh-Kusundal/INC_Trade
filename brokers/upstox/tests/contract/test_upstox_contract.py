"""Upstox broker contract tests.

Verifies that UpstoxBrokerGateway conforms to the frozen v1.0 MarketDataGateway contract.
Subclasses BrokerContractSuite to inherit all 16 contract tests.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from brokers.common.contracts.broker_contract import BrokerContractSuite
from brokers.upstox.gateway import UpstoxBrokerGateway
from domain import (
    Balance,
    DepthLevel,
    MarketDepth,
    Quote,
)
from tests.integration.fixtures.upstox import make_mock_broker


class TestUpstoxContract(BrokerContractSuite):
    """Contract tests for UpstoxBrokerGateway.

    Inherits all 16 contract tests from BrokerContractSuite:
    - Lifecycle: test_gateway_is_market_data_gateway, test_describe_returns_dict, test_capabilities_returns_broker_capabilities
    - Market Data: test_quote_returns_quote, test_ltp_returns_decimal, test_depth_returns_market_depth, test_history_returns_dataframe, test_option_chain_returns_dict, test_future_chain_returns_dict
    - Trading: test_get_orderbook_returns_list, test_get_trade_book_returns_list
    - Portfolio: test_positions_returns_list, test_holdings_returns_list, test_funds_returns_balance, test_trades_returns_list
    - Instrument: test_search_returns_list
    - Order Status: test_order_status_normalization_contract
    """

    @pytest.fixture
    def gateway(self) -> UpstoxBrokerGateway:
        """Provide an UpstoxBrokerGateway backed by a mock broker."""
        mock_broker = make_mock_broker(ws_connected=False, allow_live_orders=False)
        return UpstoxBrokerGateway(mock_broker)

    # ── Override market data tests with Upstox-specific mocks ──────────────

    def test_quote_returns_quote(self, gateway: UpstoxBrokerGateway) -> None:
        """Override to mock Upstox quote response."""
        # Mock the adapter's quote method
        gateway._market_data.quote = MagicMock(
            return_value=Quote(
                symbol="RELIANCE",
                ltp=Decimal("2550.00"),
                open=Decimal("2540.00"),
                high=Decimal("2560.00"),
                low=Decimal("2535.00"),
                close=Decimal("2545.00"),
                volume=500000,
            )
        )
        result = gateway.quote("RELIANCE", "NSE")
        assert isinstance(result, Quote)
        assert result.symbol == "RELIANCE"
        assert isinstance(result.ltp, Decimal)

    def test_ltp_returns_decimal(self, gateway: UpstoxBrokerGateway) -> None:
        """Override to mock Upstox LTP response."""
        gateway._market_data.ltp = MagicMock(return_value=Decimal("2550.00"))
        result = gateway.ltp("RELIANCE", "NSE")
        assert isinstance(result, Decimal)
        assert result >= Decimal("0")

    def test_depth_returns_market_depth(self, gateway: UpstoxBrokerGateway) -> None:
        """Override to mock Upstox depth response."""
        gateway._market_data.depth = MagicMock(
            return_value=MarketDepth(
                symbol="RELIANCE",
                bids=[DepthLevel(price=Decimal("2550.00"), quantity=100, orders=5)],
                asks=[DepthLevel(price=Decimal("2551.00"), quantity=150, orders=3)],
            )
        )
        result = gateway.depth("RELIANCE", "NSE")
        assert isinstance(result, MarketDepth)
        assert result.bids is not None
        assert result.asks is not None
        if result.bids:
            assert isinstance(result.bids[0], DepthLevel)

    def test_positions_returns_list(self, gateway: UpstoxBrokerGateway) -> None:
        """Override to mock Upstox positions response."""
        gateway._portfolio.get_positions = MagicMock(return_value=[])
        result = gateway.positions()
        assert isinstance(result, list)

    def test_holdings_returns_list(self, gateway: UpstoxBrokerGateway) -> None:
        """Override to mock Upstox holdings response."""
        gateway._portfolio.get_holdings = MagicMock(return_value=[])
        result = gateway.holdings()
        assert isinstance(result, list)

    def test_funds_returns_balance(self, gateway: UpstoxBrokerGateway) -> None:
        """Override to mock Upstox funds response."""
        gateway._portfolio.get_funds = MagicMock(
            return_value=Balance(
                available_balance=Decimal("100000.00"),
                used_margin=Decimal("0.00"),
            )
        )
        result = gateway.funds()
        assert isinstance(result, Balance)
        assert result.available_balance >= Decimal("0")

    def test_option_chain_returns_dict(self, gateway: UpstoxBrokerGateway) -> None:
        from domain import OptionChain

        gateway._broker.options.get_option_chain.return_value = []
        gateway._broker.options.get_expiries.return_value = ["2025-06-26"]
        result = gateway.option_chain("NIFTY", "NFO")
        if isinstance(result, OptionChain):
            result = result.to_dict()
        assert isinstance(result, dict)
        assert "underlying" in result

    def test_future_chain_returns_dict(self, gateway: UpstoxBrokerGateway) -> None:
        """Override to mock Upstox futures adapter."""
        gateway._broker.futures.get_contracts.return_value = [
            {
                "expiry": "2025-06-26",
                "symbol": "NIFTY25JUNFUT",
                "lot_size": 25,
                "underlying": "NIFTY",
            }
        ]
        gateway._broker.futures.get_expiries.return_value = ["2025-06-26"]
        result = gateway.future_chain("NIFTY", "NFO")
        from domain import FutureChain

        if isinstance(result, FutureChain):
            result = result.to_dict()
        assert isinstance(result, dict)
        assert result.get("underlying") == "NIFTY"
        assert result.get("contracts")
