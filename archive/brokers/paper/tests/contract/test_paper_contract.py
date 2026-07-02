"""Paper broker contract tests.

Verifies that PaperGateway conforms to the frozen v1.0 MarketDataGateway contract.
Subclasses BrokerContractSuite to inherit all 16 contract tests.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from brokers.common.contracts.broker_contract import BrokerContractSuite
from brokers.paper.paper_gateway import PaperGateway


class TestPaperContract(BrokerContractSuite):
    """Contract tests for PaperGateway.

    Inherits all 16 contract tests from BrokerContractSuite:
    - Lifecycle: test_gateway_is_market_data_gateway, test_describe_returns_dict, test_capabilities_returns_broker_capabilities
    - Market Data: test_quote_returns_quote, test_ltp_returns_decimal, test_depth_returns_market_depth, test_history_returns_dataframe, test_option_chain_returns_dict, test_future_chain_returns_dict
    - Trading: test_get_orderbook_returns_list, test_get_trade_book_returns_list
    - Portfolio: test_positions_returns_list, test_holdings_returns_list, test_funds_returns_balance, test_trades_returns_list
    - Instrument: test_search_returns_list
    - Order Status: test_order_status_normalization_contract

    PaperGateway provides deterministic simulation, so all tests should pass
    without mocking.
    """

    @pytest.fixture
    def gateway(self) -> PaperGateway:
        """Provide a PaperGateway instance with default capital."""
        return PaperGateway(initial_capital=Decimal("1000000"))
