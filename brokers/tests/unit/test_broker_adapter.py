"""Tests for BrokerAdapter protocol and concrete implementations (Phase 2).

Covers:
- BrokerAdapter protocol is @runtime_checkable
- DhanAdapter, UpstoxAdapter, PaperAdapter satisfy the protocol
- Adapter lifecycle (connect/disconnect)
- Provider method delegation to gateway
- Pre-connect guard raises RuntimeError
- Instrument factory integration
- Depth defaults per broker
- PaperAdapter specific features (set_quote)
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from inc_trade.adapters.broker_adapter import BrokerAdapter
from inc_trade.adapters.dhan import DhanAdapter
from inc_trade.adapters.paper import PaperAdapter
from inc_trade.adapters.upstox import UpstoxAdapter
from inc_trade.domain.entities import MarketDepth, Quote
from inc_trade.market.depth_decorators import (
    Depth30Decorator,
    Depth200Decorator,
)
from inc_trade.ports.providers import (
    DepthProvider,
    HistoricalDataProvider,
    InstrumentDataProvider,
    OrderProvider,
    StreamingDataProvider,
)

# ── Protocol Satisfaction Tests ─────────────────────────────────────────


class TestBrokerAdapterProtocol:
    """BrokerAdapter must be @runtime_checkable and correctly typed."""

    def test_is_runtime_checkable(self) -> None:
        """BrokerAdapter protocol should be runtime checkable."""
        assert isinstance(BrokerAdapter, type)
        assert hasattr(BrokerAdapter, "__instancecheck__")

    def test_dhan_adapter_satisfies_protocol(self) -> None:
        """DhanAdapter should satisfy BrokerAdapter via isinstance."""
        adapter = DhanAdapter(client_id="test", access_token="test")
        assert isinstance(adapter, BrokerAdapter)

    def test_upstox_adapter_satisfies_protocol(self) -> None:
        """UpstoxAdapter should satisfy BrokerAdapter via isinstance."""
        adapter = UpstoxAdapter(access_token="test")
        assert isinstance(adapter, BrokerAdapter)

    def test_paper_adapter_satisfies_protocol(self) -> None:
        """PaperAdapter should satisfy BrokerAdapter via isinstance."""
        adapter = PaperAdapter()
        assert isinstance(adapter, BrokerAdapter)

    def test_dhan_satisfies_all_provider_protocols(self) -> None:
        """DhanAdapter should satisfy all five provider protocols."""
        adapter = DhanAdapter(client_id="test", access_token="test")
        assert isinstance(adapter, InstrumentDataProvider)
        assert isinstance(adapter, DepthProvider)
        assert isinstance(adapter, HistoricalDataProvider)
        assert isinstance(adapter, StreamingDataProvider)
        assert isinstance(adapter, OrderProvider)

    def test_upstox_satisfies_all_provider_protocols(self) -> None:
        """UpstoxAdapter should satisfy all five provider protocols."""
        adapter = UpstoxAdapter(access_token="test")
        assert isinstance(adapter, InstrumentDataProvider)
        assert isinstance(adapter, DepthProvider)
        assert isinstance(adapter, HistoricalDataProvider)
        assert isinstance(adapter, StreamingDataProvider)
        assert isinstance(adapter, OrderProvider)

    def test_paper_satisfies_all_provider_protocols(self) -> None:
        """PaperAdapter should satisfy all five provider protocols."""
        adapter = PaperAdapter()
        assert isinstance(adapter, InstrumentDataProvider)
        assert isinstance(adapter, DepthProvider)
        assert isinstance(adapter, HistoricalDataProvider)
        assert isinstance(adapter, StreamingDataProvider)
        assert isinstance(adapter, OrderProvider)


# ── Broker Identity Tests ────────────────────────────────────────────────


class TestBrokerIdentity:
    """Each adapter must correctly report its broker_id and max_levels."""

    def test_dhan_broker_id(self) -> None:
        assert DhanAdapter().broker_id == "dhan"

    def test_upstox_broker_id(self) -> None:
        assert UpstoxAdapter().broker_id == "upstox"

    def test_paper_broker_id(self) -> None:
        assert PaperAdapter().broker_id == "paper"

    def test_dhan_max_levels(self) -> None:
        assert DhanAdapter().max_levels == 200

    def test_upstox_max_levels(self) -> None:
        assert UpstoxAdapter().max_levels == 30

    def test_paper_max_levels(self) -> None:
        assert PaperAdapter().max_levels == 5


# ── Adapter Lifecycle Tests ──────────────────────────────────────────────


class TestAdapterLifecycle:
    """Adapters must correctly transition through connect/disconnect."""

    def test_dhan_not_connected_after_init(self) -> None:
        adapter = DhanAdapter()
        assert not adapter.is_connected

    def test_upstox_not_connected_after_init(self) -> None:
        adapter = UpstoxAdapter()
        assert not adapter.is_connected

    def test_paper_not_connected_after_init(self) -> None:
        adapter = PaperAdapter()
        assert not adapter.is_connected

    def test_paper_connect_and_disconnect(self) -> None:
        """PaperAdapter connect/disconnect should work without credentials."""
        adapter = PaperAdapter()
        adapter.connect()
        assert adapter.is_connected
        adapter.disconnect()
        assert not adapter.is_connected

    def test_dhan_connect_with_mock_gateway(self) -> None:
        """DhanAdapter.connect() should create and store the gateway."""
        with patch("brokers.adapters.dhan.gateway.DhanGateway") as mock_gw:
            mock_instance = MagicMock()
            mock_gw.return_value = mock_instance
            mock_instance.streaming.is_connected = True

            adapter = DhanAdapter(client_id="test", access_token="test")
            adapter.connect()

            mock_gw.assert_called_once_with(
                client_id="test",
                access_token="test",
            )
            assert adapter.is_connected

    def test_upstox_connect_with_mock_gateway(self) -> None:
        """UpstoxAdapter.connect() should create and store the gateway."""
        with patch("brokers.adapters.upstox.gateway.UpstoxGateway") as mock_gw:
            mock_instance = MagicMock()
            mock_gw.return_value = mock_instance
            mock_instance.streaming.is_connected = True

            adapter = UpstoxAdapter(access_token="test")
            adapter.connect()

            mock_gw.assert_called_once_with(access_token="test")
            assert adapter.is_connected


# ── Pre-Connect Guard Tests ──────────────────────────────────────────────


class TestPreConnectGuard:
    """Calling provider methods before connect() should raise RuntimeError."""

    @pytest.fixture(
        params=[
            ("dhan", lambda: DhanAdapter()),
            ("upstox", lambda: UpstoxAdapter()),
            ("paper", lambda: PaperAdapter()),
        ]
    )
    def disconnected_adapter(self, request):
        _, factory = request.param
        return factory()

    def test_quote_raises(self, disconnected_adapter) -> None:
        with pytest.raises(RuntimeError, match="not connected"):
            disconnected_adapter.quote("RELIANCE", "NSE")

    def test_ltp_raises(self, disconnected_adapter) -> None:
        with pytest.raises(RuntimeError, match="not connected"):
            disconnected_adapter.ltp("RELIANCE", "NSE")

    def test_depth_raises(self, disconnected_adapter) -> None:
        with pytest.raises(RuntimeError, match="not connected"):
            disconnected_adapter.depth("RELIANCE", "NSE")

    def test_place_order_raises(self, disconnected_adapter) -> None:
        with pytest.raises(RuntimeError, match="not connected"):
            disconnected_adapter.place_order("RELIANCE", "NSE", "BUY", 10)

    def test_get_candles_raises(self, disconnected_adapter) -> None:
        import datetime

        with pytest.raises(RuntimeError, match="not connected"):
            disconnected_adapter.get_candles(
                "RELIANCE",
                "NSE",
                datetime.datetime.now(),
                datetime.datetime.now(),
                "1D",
            )


# ── Provider Method Delegation Tests ─────────────────────────────────────


class TestDhanAdapterProviderMethods:
    """DhanAdapter must delegate to the correct gateway sub-services."""

    @pytest.fixture
    def adapter(self):
        with patch("brokers.adapters.dhan.gateway.DhanGateway") as mock_gw:
            mock_instance = MagicMock()
            mock_gw.return_value = mock_instance
            mock_instance.streaming.is_connected = True
            adapter = DhanAdapter(client_id="test", access_token="test")
            adapter.connect()
            yield adapter, mock_instance

    def test_quote_delegates_to_market_data(self, adapter) -> None:
        a, gw = adapter
        gw.market_data.quote.return_value = Quote(symbol="RELIANCE", ltp=Decimal("2500"))
        result = a.quote("RELIANCE", "NSE")
        gw.market_data.quote.assert_called_once_with("RELIANCE", "NSE")
        assert result.ltp == Decimal("2500")

    def test_ltp_delegates_to_market_data(self, adapter) -> None:
        a, gw = adapter
        gw.market_data.ltp.return_value = Decimal("2500")
        result = a.ltp("RELIANCE", "NSE")
        gw.market_data.ltp.assert_called_once_with("RELIANCE", "NSE")
        assert result == Decimal("2500")

    def test_depth_delegates_to_market_data(self, adapter) -> None:
        a, gw = adapter
        gw.market_data.depth.return_value = MarketDepth(symbol="RELIANCE")
        result = a.depth("RELIANCE", "NSE", levels=200)
        gw.market_data.depth.assert_called_once_with("RELIANCE", "NSE")
        assert result.symbol == "RELIANCE"

    def test_get_candles_delegates_to_historical(self, adapter) -> None:
        a, gw = adapter
        import datetime

        start = datetime.datetime(2025, 1, 1)
        end = datetime.datetime(2025, 1, 2)
        gw.historical.get_candles.return_value = []
        result = a.get_candles("RELIANCE", "NSE", start, end, "1D")
        gw.historical.get_candles.assert_called_once_with(
            "RELIANCE",
            "NSE",
            start,
            end,
            "1D",
        )
        assert result == []

    def test_place_order_delegates_to_orders(self, adapter) -> None:
        a, gw = adapter
        gw.orders.place_order.return_value = {"order_id": "ORD001", "success": True}
        result = a.place_order("RELIANCE", "NSE", "BUY", 10)
        gw.orders.place_order.assert_called_once()
        assert result["order_id"] == "ORD001"

    def test_cancel_order_delegates_to_orders(self, adapter) -> None:
        a, gw = adapter
        gw.orders.cancel_order.return_value = {"order_id": "ORD001", "success": True}
        result = a.cancel_order("ORD001")
        gw.orders.cancel_order.assert_called_once_with("ORD001")
        assert result["success"]


class TestUpstoxAdapterProviderMethods:
    """UpstoxAdapter must delegate to the correct gateway sub-services."""

    @pytest.fixture
    def adapter(self):
        with patch("brokers.adapters.upstox.gateway.UpstoxGateway") as mock_gw:
            mock_instance = MagicMock()
            mock_gw.return_value = mock_instance
            mock_instance.streaming.is_connected = True
            adapter = UpstoxAdapter(access_token="test")
            adapter.connect()
            yield adapter, mock_instance

    def test_quote_delegates_to_market_data(self, adapter) -> None:
        a, gw = adapter
        gw.market_data.quote.return_value = Quote(symbol="RELIANCE", ltp=Decimal("1800"))
        result = a.quote("RELIANCE", "NSE")
        gw.market_data.quote.assert_called_once_with("RELIANCE", "NSE")
        assert result.ltp == Decimal("1800")

    def test_ltp_delegates_to_market_data(self, adapter) -> None:
        a, gw = adapter
        gw.market_data.ltp.return_value = Decimal("1800")
        result = a.ltp("RELIANCE", "NSE")
        gw.market_data.ltp.assert_called_once_with("RELIANCE", "NSE")
        assert result == Decimal("1800")

    def test_depth_delegates_to_market_data(self, adapter) -> None:
        a, gw = adapter
        gw.market_data.depth.return_value = MarketDepth(symbol="RELIANCE")
        result = a.depth("RELIANCE", "NSE", levels=30)
        gw.market_data.depth.assert_called_once_with("RELIANCE", "NSE")
        assert result.symbol == "RELIANCE"


class TestPaperAdapterProviderMethods:
    """PaperAdapter must delegate to the correct gateway sub-services."""

    @pytest.fixture
    def adapter(self):
        adapter = PaperAdapter()
        adapter.connect()
        return adapter

    def test_quote_returns_default(self, adapter) -> None:
        result = adapter.quote("RELIANCE", "NSE")
        assert isinstance(result, Quote)
        assert result.symbol == "RELIANCE"
        assert result.ltp == Decimal("100.00")

    def test_set_quote_then_quote(self, adapter) -> None:
        adapter.set_quote("RELIANCE", Decimal("2500"))
        result = adapter.quote("RELIANCE", "NSE")
        assert result.ltp == Decimal("2500")

    def test_ltp_returns_default(self, adapter) -> None:
        result = adapter.ltp("RELIANCE", "NSE")
        assert result == Decimal("100.00")

    def test_set_quote_then_ltp(self, adapter) -> None:
        adapter.set_quote("RELIANCE", Decimal("2500"))
        result = adapter.ltp("RELIANCE", "NSE")
        assert result == Decimal("2500")

    def test_depth_returns_empty(self, adapter) -> None:
        result = adapter.depth("RELIANCE", "NSE")
        assert isinstance(result, MarketDepth)
        assert result.symbol == "RELIANCE"

    def test_place_order_returns_order_response(self, adapter) -> None:
        result = adapter.place_order("RELIANCE", "NSE", "BUY", 10)
        assert result.success is True
        assert result.order_id.startswith("PAPER-")

    def test_cancel_order(self, adapter) -> None:
        placed = adapter.place_order("RELIANCE", "NSE", "BUY", 10)
        result = adapter.cancel_order(placed.order_id)
        assert result.success is True


# ── Instrument Factory Integration Tests ─────────────────────────────────


class TestAdapterInstrumentFactory:
    """Adapters must create Instruments with providers injected correctly."""

    def test_dhan_instrument_has_provider(self) -> None:
        with patch("brokers.adapters.dhan.gateway.DhanGateway") as mock_gw:
            mock_instance = MagicMock()
            mock_gw.return_value = mock_instance
            mock_instance.streaming.is_connected = True

            adapter = DhanAdapter(client_id="test", access_token="test")
            adapter.connect()
            inst = adapter.instrument("RELIANCE", "NSE")

            assert inst._provider is adapter
            assert inst._depth_provider is adapter
            assert inst._order_provider is adapter
            assert inst._historical_provider is adapter
            assert inst._streaming_provider is adapter

    def test_dhan_instrument_has_depth200_decorator(self) -> None:
        """DhanAdapter should automatically apply Depth200Decorator."""
        with patch("brokers.adapters.dhan.gateway.DhanGateway") as mock_gw:
            mock_instance = MagicMock()
            mock_gw.return_value = mock_instance
            mock_instance.streaming.is_connected = True

            adapter = DhanAdapter(client_id="test", access_token="test")
            adapter.connect()
            inst = adapter.instrument("RELIANCE", "NSE")

            assert isinstance(inst, Depth200Decorator)

    def test_upstox_instrument_has_depth30_decorator(self) -> None:
        """UpstoxAdapter should automatically apply Depth30Decorator."""
        with patch("brokers.adapters.upstox.gateway.UpstoxGateway") as mock_gw:
            mock_instance = MagicMock()
            mock_gw.return_value = mock_instance
            mock_instance.streaming.is_connected = True

            adapter = UpstoxAdapter(access_token="test")
            adapter.connect()
            inst = adapter.instrument("RELIANCE", "NSE")

            assert isinstance(inst, Depth30Decorator)

    def test_paper_instrument_no_depth_decorator(self) -> None:
        """PaperAdapter should NOT apply any depth decorator."""
        adapter = PaperAdapter()
        adapter.connect()
        inst = adapter.instrument("RELIANCE", "NSE")

        from inc_trade.market.decorators import InstrumentDecorator

        assert not isinstance(inst, InstrumentDecorator)

    def test_paper_instrument_can_quote_and_order(self) -> None:
        """Instruments from PaperAdapter should support quote + order."""
        adapter = PaperAdapter()
        adapter.connect()

        inst = adapter.instrument("RELIANCE", "NSE")
        quote = inst.quote()
        assert quote.ltp == Decimal("100.00")

        order = inst.buy(quantity=10)
        assert order.success

    def test_dhan_instrument_can_quote_and_depth(self) -> None:
        """Instruments from DhanAdapter should support quote + depth via decorator."""
        with patch("brokers.adapters.dhan.gateway.DhanGateway") as mock_gw:
            mock_instance = MagicMock()
            mock_gw.return_value = mock_instance
            mock_instance.streaming.is_connected = True
            mock_instance.market_data.quote.return_value = Quote(
                symbol="RELIANCE",
                ltp=Decimal("2500"),
            )
            mock_instance.market_data.depth.return_value = MarketDepth(symbol="RELIANCE")

            adapter = DhanAdapter(client_id="test", access_token="test")
            adapter.connect()
            inst = adapter.instrument("RELIANCE", "NSE")

            quote = inst.quote()
            assert quote.ltp == Decimal("2500")

            depth = inst.depth(200)
            assert depth.symbol == "RELIANCE"

    def test_instrument_buy_delegates_to_adapter(self) -> None:
        """inst.buy() should delegate to the adapter's place_order."""
        with patch("brokers.adapters.dhan.gateway.DhanGateway") as mock_gw:
            mock_instance = MagicMock()
            mock_gw.return_value = mock_instance
            mock_instance.streaming.is_connected = True
            mock_instance.orders.place_order.return_value = {
                "order_id": "ORD001",
                "success": True,
            }

            adapter = DhanAdapter(client_id="test", access_token="test")
            adapter.connect()
            inst = adapter.instrument("RELIANCE", "NSE")
            order = inst.buy(quantity=10)

            mock_instance.orders.place_order.assert_called_once()
            assert order["order_id"] == "ORD001"


# ── Depth Override Tests ─────────────────────────────────────────────────


class TestDepthOverride:
    """User-specified apply_depth should override broker defaults."""

    def test_dhan_custom_apply_depth(self) -> None:
        """User can override Dhan default depth of 200."""
        with patch("brokers.adapters.dhan.gateway.DhanGateway") as mock_gw:
            mock_instance = MagicMock()
            mock_gw.return_value = mock_instance
            mock_instance.streaming.is_connected = True

            adapter = DhanAdapter(client_id="test", access_token="test")
            adapter.connect()
            inst = adapter.instrument("RELIANCE", "NSE", apply_depth=5)

            from inc_trade.market.decorators import InstrumentDecorator

            assert not isinstance(inst, InstrumentDecorator)

    def test_upstox_custom_apply_depth(self) -> None:
        """User can override Upstox default depth of 30."""
        with patch("brokers.adapters.upstox.gateway.UpstoxGateway") as mock_gw:
            mock_instance = MagicMock()
            mock_gw.return_value = mock_instance
            mock_instance.streaming.is_connected = True

            adapter = UpstoxAdapter(access_token="test")
            adapter.connect()
            inst = adapter.instrument("RELIANCE", "NSE", apply_depth=5)

            from inc_trade.market.decorators import InstrumentDecorator

            assert not isinstance(inst, InstrumentDecorator)


# ── Edge Cases ───────────────────────────────────────────────────────────


class TestEdgeCases:
    """Edge cases for adapter behavior."""

    def test_double_disconnect_safe(self) -> None:
        """Calling disconnect twice should not raise."""
        adapter = PaperAdapter()
        adapter.connect()
        adapter.disconnect()
        adapter.disconnect()  # should not raise

    def test_paper_connect_twice(self) -> None:
        """Connecting twice should work (creates new gateway)."""
        adapter = PaperAdapter()
        adapter.connect()
        gw1 = adapter._gw
        adapter.connect()
        gw2 = adapter._gw
        assert gw1 is not gw2  # New gateway created

    def test_dhan_quote_batch_delegates(self) -> None:
        """quote_batch should delegate to market_data.quote_batch."""
        with patch("brokers.adapters.dhan.gateway.DhanGateway") as mock_gw:
            mock_instance = MagicMock()
            mock_gw.return_value = mock_instance
            mock_instance.streaming.is_connected = True
            mock_instance.market_data.quote_batch.return_value = {}

            adapter = DhanAdapter(client_id="test", access_token="test")
            adapter.connect()
            result = adapter.quote_batch(["RELIANCE", "TCS"], "NSE")
            mock_instance.market_data.quote_batch.assert_called_once_with(
                ["RELIANCE", "TCS"],
                "NSE",
            )
            assert result == {}

    def test_paper_adapter_raises_on_historical(self) -> None:
        """PaperAdapter.get_candles should raise NotSupportedError."""
        import datetime

        from inc_trade.domain.exceptions import NotSupportedError

        adapter = PaperAdapter()
        adapter.connect()
        with pytest.raises(NotSupportedError):
            adapter.get_candles(
                "RELIANCE",
                "NSE",
                datetime.datetime.now(),
                datetime.datetime.now(),
                "1D",
            )


# ── Architecture Constraint Tests ────────────────────────────────────────


class TestAdapterArchitecture:
    """Adapters should not violate architectural boundaries."""

    def test_adapter_imports_gateway_only_at_runtime(self) -> None:
        """Importing inc_trade.adapters.dhan should NOT import the gateway
        at module level. Gateway is imported lazily inside connect()."""
        import importlib
        import sys

        # Remove any cached modules
        for mod in list(sys.modules.keys()):
            if "dhan" in mod.lower() and "broker_adapter" not in mod:
                sys.modules.pop(mod, None)

        # Clear broker-specific modules
        for mod in list(sys.modules.keys()):
            if "brokers.adapters.dhan" in mod:
                sys.modules.pop(mod, None)

        importlib.import_module("inc_trade.adapters.dhan")

        # The brokers.adapters.dhan.gateway should NOT be loaded
        assert "brokers.adapters.dhan.gateway" not in sys.modules
        assert "brokers.adapters.dhan" not in sys.modules
