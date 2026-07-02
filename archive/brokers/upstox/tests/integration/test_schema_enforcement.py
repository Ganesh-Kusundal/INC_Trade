"""Schema enforcement tests for Upstox broker endpoints.

Ensures all endpoints return data with the correct schema.
Catches broker API changes that break the contract.

These tests require a valid .env.upstox with UPSTOX_API_KEY and UPSTOX_ACCESS_TOKEN.
They are skipped automatically when the env file is absent.
"""

from __future__ import annotations

from decimal import Decimal

from brokers.upstox.tests.integration.conftest import skip_live


@skip_live
class TestSchemaEnforcement:
    """Schema enforcement tests for all Upstox endpoint responses."""

    def test_quote_schema(self, gateway):
        """Quote must have: symbol, ltp, open, high, low, close, volume, change."""
        quote = gateway.quote("RELIANCE", "NSE")
        required_fields = ["symbol", "ltp", "open", "high", "low", "close", "volume", "change"]
        for field in required_fields:
            assert hasattr(quote, field), f"Quote missing field: {field}"
        # Type checks
        assert isinstance(quote.ltp, (int, float, Decimal))
        assert isinstance(quote.volume, (int, float))

    def test_market_depth_schema(self, gateway):
        """MarketDepth must have: bids (list), asks (list)."""
        depth = gateway.depth("RELIANCE", "NSE")
        assert hasattr(depth, "bids")
        assert hasattr(depth, "asks")
        assert isinstance(depth.bids, list)
        assert isinstance(depth.asks, list)
        # DepthLevel schema
        if depth.bids:
            level = depth.bids[0]
            assert hasattr(level, "price")
            assert hasattr(level, "quantity")
            assert hasattr(level, "orders")

    def test_balance_schema(self, gateway):
        """Balance must have: available_balance, used_margin, total_margin."""
        balance = gateway.funds()
        required_fields = ["available_balance", "used_margin", "total_margin"]
        for field in required_fields:
            assert hasattr(balance, field), f"Balance missing field: {field}"
        # Type checks
        assert isinstance(balance.available_balance, (int, float, Decimal))

    def test_order_schema(self, gateway):
        """Order must have: order_id, symbol, exchange, side, quantity, status."""
        orderbook = gateway.get_orderbook()
        if orderbook:
            order = orderbook[0]
            required_fields = ["order_id", "symbol", "exchange", "side", "quantity", "status"]
            for field in required_fields:
                assert hasattr(order, field), f"Order missing field: {field}"

    def test_position_schema(self, gateway):
        """Position must have: symbol, exchange, quantity, average_price."""
        positions = gateway.positions()
        if positions:
            pos = positions[0]
            required_fields = ["symbol", "exchange", "quantity", "average_price"]
            for field in required_fields:
                assert hasattr(pos, field), f"Position missing field: {field}"

    def test_holding_schema(self, gateway):
        """Holding must have: symbol, exchange, quantity."""
        holdings = gateway.holdings()
        if holdings:
            holding = holdings[0]
            required_fields = ["symbol", "exchange", "quantity"]
            for field in required_fields:
                assert hasattr(holding, field), f"Holding missing field: {field}"

    def test_trade_schema(self, gateway):
        """Trade must have: symbol, exchange, quantity, price."""
        trades = gateway.trades()
        if trades:
            trade = trades[0]
            required_fields = ["symbol", "exchange", "quantity", "price"]
            for field in required_fields:
                assert hasattr(trade, field), f"Trade missing field: {field}"

    def test_history_dataframe_schema(self, gateway):
        """history() DataFrame must have: timestamp, open, high, low, close, volume."""
        df = gateway.history("RELIANCE", "NSE", timeframe="1D", lookback_days=3)
        required_cols = ["timestamp", "open", "high", "low", "close", "volume"]
        for col in required_cols:
            assert col in df.columns, f"History DataFrame missing column: {col}"

    def test_option_chain_schema(self, gateway):
        """OptionChain must have: underlying, exchange, expiry, strikes."""
        expiries = gateway._broker.options.get_expiries("NIFTY", "NFO")
        if expiries:
            chain = gateway.option_chain("NIFTY", "NFO", expiry=expiries[0])
            assert hasattr(chain, "underlying")
            assert hasattr(chain, "exchange")
            assert hasattr(chain, "expiry")
            data = chain.to_dict() if hasattr(chain, "to_dict") else chain
            assert "strikes" in data

    def test_future_chain_schema(self, gateway):
        """FutureChain must have: underlying, expiries, contracts."""
        chain = gateway.future_chain("NIFTY", "NFO")
        assert hasattr(chain, "underlying")
        assert hasattr(chain, "expiries")
        assert hasattr(chain, "contracts")
        assert chain.underlying
        assert isinstance(chain.expiries, (list, tuple))
        assert isinstance(chain.contracts, (list, tuple))

    def test_search_result_schema(self, gateway):
        """Search results must have: symbol, exchange."""
        results = gateway.search("RELIANCE")
        if results:
            result = results[0]
            required_fields = ["symbol", "exchange"]
            for field in required_fields:
                assert field in result, f"Search result missing field: {field}"

    def test_order_response_schema(self, gateway):
        """OrderResponse must have: success, message."""
        response = gateway.place_order(
            symbol="INVALID123",
            exchange="NSE",
            side="BUY",
            quantity=1,
            order_type="LIMIT",
            product_type="INTRADAY",
            price=Decimal("100"),
        )
        assert hasattr(response, "success")
        assert hasattr(response, "message")
        assert isinstance(response.success, bool)
