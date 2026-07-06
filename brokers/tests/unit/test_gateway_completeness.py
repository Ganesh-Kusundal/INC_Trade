"""Test that all gateway methods work correctly for all brokers."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from inc_trade.domain.enums import OrderType, ProductType, Side, Validity

from brokers.adapters.paper.gateway import PaperGateway


class TestGatewayCompleteness:
    """Test that all gateway methods are functional."""

    def test_paper_gateway_all_methods_work(self) -> None:
        """Test that PaperGateway implements all required methods."""
        gateway = PaperGateway()

        # Test broker_id
        assert gateway.broker_id.value == "paper"

        # Test capabilities
        caps = gateway.capabilities()
        assert caps.supports_place_order
        assert caps.supports_cancel_order
        assert caps.supports_modify_order

        # Test orders
        resp = gateway.orders.place_order(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            order_type=OrderType.MARKET,
            price=Decimal("0"),
            product_type=ProductType.INTRADAY,
            validity=Validity.DAY,
            trigger_price=Decimal("0"),
        )
        assert resp.success
        assert resp.order_id

        # Test order cancellation
        cancel_resp = gateway.orders.cancel_order(resp.order_id)
        assert cancel_resp.success

        # Test get_order
        order = gateway.orders.get_order(resp.order_id)
        assert order is not None
        assert order.order_id == resp.order_id

        # Test get_orderbook
        orderbook = gateway.orders.get_orderbook()
        assert isinstance(orderbook, list)

        # Test market data
        gateway.set_quote("RELIANCE", Decimal("2500"))

        ltp = gateway.market_data.ltp("RELIANCE", "NSE")
        assert ltp == Decimal("2500")

        quote = gateway.market_data.quote("RELIANCE", "NSE")
        assert quote.symbol == "RELIANCE"
        assert quote.ltp == Decimal("2500")

        depth = gateway.market_data.depth("RELIANCE", "NSE")
        assert depth.symbol == "RELIANCE"

        # Test batch methods
        batch_ltp = gateway.market_data.ltp_batch(["RELIANCE", "TCS"], "NSE")
        assert "RELIANCE" in batch_ltp
        assert batch_ltp["RELIANCE"] == Decimal("2500")

        batch_quotes = gateway.market_data.quote_batch(["RELIANCE"], "NSE")
        assert "RELIANCE" in batch_quotes

        # Test portfolio
        positions = gateway.portfolio.positions()
        assert isinstance(positions, list)

        holdings = gateway.portfolio.holdings()
        assert isinstance(holdings, list)

        funds = gateway.portfolio.funds()
        assert funds.available_cash == Decimal("1000000.00")

        trades = gateway.portfolio.trades()
        assert isinstance(trades, list)

        # Test historical data
        end_time = datetime.now()
        start_time = end_time - timedelta(days=7)

        import pytest
        from inc_trade.domain.exceptions import NotSupportedError

        with pytest.raises(NotSupportedError):
            candles = gateway.historical.get_historical_candles(
                symbol="RELIANCE",
                exchange="NSE",
                start_time=start_time,
                end_time=end_time,
                resolution="1D",
            )

        # Test instruments
        results = gateway.instruments.search("RELIANCE")
        assert isinstance(results, list)

        # Test auth
        assert gateway.auth.is_authenticated()

        # Test streaming
        assert gateway.streaming.is_connected

        # Test extensions
        extensions = gateway.extensions
        assert extensions is not None

        # Test close
        gateway.close()

    def test_paper_gateway_service_methods_work(self) -> None:
        """Test that service methods work through the gateway."""
        gateway = PaperGateway()

        # Set up some data
        gateway.set_quote("RELIANCE", Decimal("2500"))
        gateway.set_quote("TCS", Decimal("3500"))

        # Test service methods
        resp = gateway.orders.place_order("RELIANCE", "NSE", Side.BUY, 10)
        assert resp.success

        # Test multiple orders
        resp2 = gateway.orders.place_order("TCS", "NSE", Side.SELL, 5)
        assert resp2.success

        # Test orderbook
        orders = gateway.orders.get_orderbook()
        assert len(orders) >= 2

        # Test market data services
        ltp = gateway.market_data.ltp("RELIANCE")
        assert ltp == Decimal("2500")

        quote = gateway.market_data.quote("RELIANCE")
        assert quote.ltp == Decimal("2500")

        # Test portfolio services
        positions = gateway.portfolio.positions()
        # Paper trading starts with empty positions
        assert isinstance(positions, list)

        funds = gateway.portfolio.funds()
        assert funds.available_cash >= Decimal("0")

        # Test historical services
        end_time = datetime.now()
        start_time = end_time - timedelta(days=1)

        import pytest
        from inc_trade.domain.exceptions import NotSupportedError

        with pytest.raises(NotSupportedError):
            candles = gateway.historical.get_historical_candles(
                "RELIANCE", "NSE", start_time, end_time, "1"
            )

    def test_paper_gateway_capability_patterns(self) -> None:
        """Test capability patterns work correctly."""
        gateway = PaperGateway()

        # Test capabilities
        caps = gateway.capabilities()

        # Test supports method
        assert caps.supports("place_order")
        assert caps.supports("cancel_order")
        assert caps.supports("modify_order")

        # Test negative features
        assert not caps.supports_live_market_data
        assert not caps.supports("live_market_data")

        # Test to_dict
        d = caps.to_dict()
        assert isinstance(d, dict)
        assert d["broker_id"] == "paper"
        assert d["latency_class"] == "simulated"

    def test_paper_gateway_extension_registry(self) -> None:
        """Test that extension registry works."""
        gateway = PaperGateway()

        # Get extensions
        extensions = gateway.extensions
        assert extensions is not None

        # Extensions should be empty for paper trading
        # (no broker-specific extensions)
        assert extensions is not None
