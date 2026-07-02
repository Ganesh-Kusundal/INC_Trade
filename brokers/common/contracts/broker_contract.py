"""BrokerContractSuite — tests that verify any MarketDataGateway implementation
conforms to the frozen v1.0 contract.

Usage: subclass this in each broker's contract test directory and provide
a ``gateway`` fixture that returns a configured MarketDataGateway instance.

The method names tested here match the actual MarketDataGateway ABC
(quote, history, option_chain, etc.), not legacy names (get_quote, etc.).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pandas as pd
import pytest

from brokers.common.gateway import BrokerCapabilities, MarketDataGateway
from domain import (
    Balance,
    DepthLevel,
    MarketDepth,
    OrderStatus,
    Quote,
)


class BrokerContractSuite:
    """Contract tests for any MarketDataGateway implementation.

    Subclasses must provide a ``gateway`` fixture returning a
    configured MarketDataGateway instance.
    """

    @pytest.fixture
    def gateway(self) -> MarketDataGateway:
        raise NotImplementedError("gateway fixture must be provided by the broker implementation")

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def test_gateway_is_market_data_gateway(self, gateway: Any) -> None:
        assert isinstance(gateway, MarketDataGateway)

    def test_describe_returns_dict(self, gateway: Any) -> None:
        result = gateway.describe()
        assert isinstance(result, dict)
        assert "broker" in result

    def test_capabilities_returns_broker_capabilities(self, gateway: Any) -> None:
        caps = gateway.capabilities()
        assert isinstance(caps, BrokerCapabilities)

    # ── Market Data ───────────────────────────────────────────────────────

    def test_quote_returns_quote(self, gateway: Any) -> None:
        result = gateway.quote("RELIANCE", "NSE")
        assert isinstance(result, Quote)
        assert result.symbol == "RELIANCE"
        assert isinstance(result.ltp, Decimal)

    def test_ltp_returns_decimal(self, gateway: Any) -> None:
        result = gateway.ltp("RELIANCE", "NSE")
        assert isinstance(result, Decimal)
        assert result >= Decimal("0")

    def test_depth_returns_market_depth(self, gateway: Any) -> None:
        result = gateway.depth("RELIANCE", "NSE")
        assert isinstance(result, MarketDepth)
        assert result.bids is not None
        assert result.asks is not None
        if result.bids:
            assert isinstance(result.bids[0], DepthLevel)

    def test_history_returns_dataframe(self, gateway: Any) -> None:
        df = gateway.history("RELIANCE", "NSE", "1D", lookback_days=5)
        assert isinstance(df, pd.DataFrame)
        if not df.empty:
            expected_columns = [
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "oi",
                "symbol",
                "exchange",
                "timeframe",
            ]
            for col in expected_columns:
                assert col in df.columns, f"Missing column: {col}"
            for col in ["security_id", "instrument_token", "exchange_token"]:
                assert col not in df.columns, f"Forbidden column: {col}"

    def test_option_chain_returns_dict(self, gateway: Any) -> None:
        from domain.entities.options import OptionChain

        result = gateway.option_chain("NIFTY", "NFO")
        # Accept both domain objects and dict representations (broker flexibility)
        if isinstance(result, OptionChain):
            result = result.to_dict()
        assert isinstance(result, dict)
        assert "underlying" in result

    def test_future_chain_returns_dict(self, gateway: Any) -> None:
        from domain.entities.options import FutureChain

        result = gateway.future_chain("NIFTY", "NFO")
        if isinstance(result, FutureChain):
            result = result.to_dict()
        assert isinstance(result, dict)
        assert "underlying" in result

    # ── Trading ───────────────────────────────────────────────────────────

    def test_get_orderbook_returns_list(self, gateway: Any) -> None:
        result = gateway.get_orderbook()
        assert isinstance(result, list)

    def test_get_trade_book_returns_list(self, gateway: Any) -> None:
        result = gateway.get_trade_book()
        assert isinstance(result, list)

    # ── Portfolio ─────────────────────────────────────────────────────────

    def test_positions_returns_list(self, gateway: Any) -> None:
        result = gateway.positions()
        assert isinstance(result, list)

    def test_holdings_returns_list(self, gateway: Any) -> None:
        result = gateway.holdings()
        assert isinstance(result, list)

    def test_funds_returns_balance(self, gateway: Any) -> None:
        result = gateway.funds()
        assert isinstance(result, Balance)
        assert result.available_balance >= Decimal("0")

    def test_trades_returns_list(self, gateway: Any) -> None:
        result = gateway.trades()
        assert isinstance(result, list)

    # ── Instrument ────────────────────────────────────────────────────────

    def test_search_returns_list(self, gateway: Any) -> None:
        result = gateway.search("RELIANCE")
        assert isinstance(result, list)

    # ── Order Status Normalization ────────────────────────────────────────

    def test_order_status_normalization_contract(self) -> None:
        assert OrderStatus.normalize("EXECUTED") == OrderStatus.FILLED
        assert OrderStatus.normalize("COMPLETE") == OrderStatus.FILLED
        assert OrderStatus.normalize("TRANSIT") == OrderStatus.OPEN
        assert OrderStatus.normalize("TRIGGER PENDING") == OrderStatus.OPEN
        assert OrderStatus.normalize("PARTIALLY_EXECUTED") == OrderStatus.PARTIALLY_FILLED
        for status in OrderStatus:
            assert OrderStatus.normalize(status.value) == status
