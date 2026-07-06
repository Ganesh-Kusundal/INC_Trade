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
from brokers_core.adapters.broker_adapter import BrokerAdapter
from brokers_core.adapters.dhan import DhanAdapter
from brokers_core.adapters.paper import PaperAdapter
from brokers_core.adapters.upstox import UpstoxAdapter
from brokers_core.domain.entities import MarketDepth, Quote
from brokers_core.domain.enums import Side
from brokers_core.market.depth_decorators import (
    Depth20Decorator,
    Depth30Decorator,
    Depth200Decorator,
)
from brokers_core.ports.providers import (
    DepthProvider,
    HistoricalDataProvider,
    InstrumentDataProvider,
    OrderProvider,
    StreamingDataProvider,
)


def _connected_dhan() -> DhanAdapter:
    """DhanAdapter with mocked sub-adapters (no network)."""
    adapter = DhanAdapter(client_id="test", access_token="test")
    adapter._market_data = MagicMock()
    adapter._orders = MagicMock()
    adapter._historical = MagicMock()
    adapter._streaming = MagicMock()
    adapter._streaming.is_connected = True
    adapter._options = MagicMock()
    adapter._connected = True
    return adapter


def _connected_upstox() -> UpstoxAdapter:
    """UpstoxAdapter with mocked components (no network)."""
    adapter = UpstoxAdapter(access_token="test")
    components = MagicMock()
    components.market_data = MagicMock()
    components.orders = MagicMock()
    components.historical = MagicMock()
    components.streaming = MagicMock()
    components.streaming.is_connected = True
    components.options = MagicMock()
    adapter._components = components
    adapter._connected = True
    return adapter

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

    def test_dhan_connect_wires_sub_adapters(self) -> None:
        """DhanAdapter.connect() should wire sub-adapters without DhanGateway."""
        mock_auth = MagicMock()
        mock_auth.is_authenticated.return_value = True
        mock_auth.get_token.return_value = "token"

        with (
            patch("brokers_core.adapters.dhan.adapter.DhanAuth", return_value=mock_auth),
            patch("brokers_core.adapters.dhan.adapter.DhanInstrumentResolver") as mock_resolver_cls,
            patch("brokers_core.adapters.dhan.adapter.create_dhan_http_client"),
            patch("brokers_core.adapters.dhan.adapter.DhanConnectionManager"),
            patch("brokers_core.adapters.dhan.adapter.DhanMarketData"),
            patch("brokers_core.adapters.dhan.adapter.DhanOrders"),
            patch("brokers_core.adapters.dhan.adapter.DhanOptions"),
            patch("brokers_core.adapters.dhan.adapter.DhanHistorical"),
            patch("brokers_core.adapters.dhan.adapter.DhanStreaming") as mock_stream_cls,
            patch("brokers_core.adapters.dhan.adapter.DhanDepth20Stream"),
            patch("brokers_core.adapters.dhan.adapter.DhanDepth200Stream"),
        ):
            mock_resolver_cls.return_value = MagicMock()
            mock_stream = MagicMock()
            mock_stream.is_connected = True
            mock_stream_cls.return_value = mock_stream

            adapter = DhanAdapter(client_id="test", access_token="test")
            adapter.connect()

            assert adapter.is_connected
            assert adapter._market_data is not None
            assert adapter._orders is not None

    def test_upstox_connect_wires_components(self) -> None:
        """UpstoxAdapter.connect() should build components without UpstoxGateway."""
        mock_components = MagicMock()
        mock_components.streaming.is_connected = True

        with patch(
            "brokers_core.adapters.upstox.adapter.build_upstox_components",
            return_value=mock_components,
        ) as mock_build:
            adapter = UpstoxAdapter(access_token="test")
            adapter.connect()

            mock_build.assert_called_once()
            assert adapter.is_connected
            assert adapter._components is mock_components


# ── Pre-Connect Guard Tests ──────────────────────────────────────────────


class TestPreConnectGuard:
    """Calling provider methods before connect() should raise ConnectionError."""

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
        with pytest.raises(ConnectionError, match="not connected"):
            disconnected_adapter.quote("RELIANCE", "NSE")

    def test_ltp_raises(self, disconnected_adapter) -> None:
        with pytest.raises(ConnectionError, match="not connected"):
            disconnected_adapter.ltp("RELIANCE", "NSE")

    def test_depth_raises(self, disconnected_adapter) -> None:
        with pytest.raises(ConnectionError, match="not connected"):
            disconnected_adapter.depth("RELIANCE", "NSE")

    def test_place_order_raises(self, disconnected_adapter) -> None:
        with pytest.raises(ConnectionError, match="not connected"):
            disconnected_adapter.place_order("RELIANCE", "NSE", Side.BUY, 10)

    def test_get_candles_raises(self, disconnected_adapter) -> None:
        import datetime

        with pytest.raises(ConnectionError, match="not connected"):
            disconnected_adapter.get_candles(
                "RELIANCE",
                "NSE",
                datetime.datetime.now(),
                datetime.datetime.now(),
                "1D",
            )


# ── Provider Method Delegation Tests ─────────────────────────────────────


class TestDhanAdapterProviderMethods:
    """DhanAdapter must delegate to sub-adapters directly."""

    @pytest.fixture
    def adapter(self):
        return _connected_dhan()

    def test_quote_delegates_to_market_data(self, adapter) -> None:
        adapter._market_data.quote.return_value = Quote(symbol="RELIANCE", ltp=Decimal("2500"))
        result = adapter.quote("RELIANCE", "NSE")
        adapter._market_data.quote.assert_called_once_with("RELIANCE", "NSE")
        assert result.ltp == Decimal("2500")

    def test_ltp_delegates_to_market_data(self, adapter) -> None:
        adapter._market_data.ltp.return_value = Decimal("2500")
        result = adapter.ltp("RELIANCE", "NSE")
        adapter._market_data.ltp.assert_called_once_with("RELIANCE", "NSE")
        assert result == Decimal("2500")

    def test_depth_delegates_to_market_data(self, adapter) -> None:
        adapter._market_data.depth.return_value = MarketDepth(symbol="RELIANCE")
        result = adapter.depth("RELIANCE", "NSE", levels=200)
        adapter._market_data.depth.assert_called_once_with("RELIANCE", "NSE")
        assert result.symbol == "RELIANCE"

    def test_get_candles_delegates_to_historical(self, adapter) -> None:
        import datetime

        start = datetime.datetime(2025, 1, 1)
        end = datetime.datetime(2025, 1, 2)
        adapter._historical.get_historical_candles.return_value = []
        result = adapter.get_candles("RELIANCE", "NSE", start, end, "1D")
        adapter._historical.get_historical_candles.assert_called_once_with(
            symbol="RELIANCE",
            exchange="NSE",
            start_time=start,
            end_time=end,
            resolution="1D",
        )
        assert result == []

    def test_place_order_delegates_to_orders(self, adapter) -> None:
        adapter._orders.place_order.return_value = {"order_id": "ORD001", "success": True}
        result = adapter.place_order("RELIANCE", "NSE", Side.BUY, 10)
        adapter._orders.place_order.assert_called_once()
        assert result["order_id"] == "ORD001"

    def test_cancel_order_delegates_to_orders(self, adapter) -> None:
        adapter._orders.cancel_order.return_value = {"order_id": "ORD001", "success": True}
        result = adapter.cancel_order("ORD001")
        adapter._orders.cancel_order.assert_called_once_with("ORD001")
        assert result["success"]


class TestUpstoxAdapterProviderMethods:
    """UpstoxAdapter must delegate to sub-adapters directly."""

    @pytest.fixture
    def adapter(self):
        return _connected_upstox()

    def test_quote_delegates_to_market_data(self, adapter) -> None:
        adapter._components.market_data.quote.return_value = Quote(
            symbol="RELIANCE",
            ltp=Decimal("1800"),
        )
        result = adapter.quote("RELIANCE", "NSE")
        adapter._components.market_data.quote.assert_called_once_with("RELIANCE", "NSE")
        assert result.ltp == Decimal("1800")

    def test_ltp_delegates_to_market_data(self, adapter) -> None:
        adapter._components.market_data.ltp.return_value = Decimal("1800")
        result = adapter.ltp("RELIANCE", "NSE")
        adapter._components.market_data.ltp.assert_called_once_with("RELIANCE", "NSE")
        assert result == Decimal("1800")

    def test_depth_delegates_to_market_data(self, adapter) -> None:
        adapter._components.market_data.depth.return_value = MarketDepth(symbol="RELIANCE")
        result = adapter.depth("RELIANCE", "NSE", levels=30)
        adapter._components.market_data.depth.assert_called_once_with("RELIANCE", "NSE")
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
        result = adapter.place_order("RELIANCE", "NSE", Side.BUY, 10)
        assert result.success is True
        assert result.order_id.startswith("PAPER-")

    def test_cancel_order(self, adapter) -> None:
        placed = adapter.place_order("RELIANCE", "NSE", Side.BUY, 10)
        result = adapter.cancel_order(placed.order_id)
        assert result.success is True


# ── Instrument Factory Integration Tests ─────────────────────────────────


class TestAdapterInstrumentFactory:
    """Adapters must create Instruments with providers injected correctly."""

    def test_dhan_instrument_has_provider(self) -> None:
        adapter = _connected_dhan()
        inst = adapter.instrument("RELIANCE", "NSE")

        assert inst._provider is adapter
        assert inst._depth_provider is adapter
        assert inst._order_provider is adapter
        assert inst._historical_provider is adapter
        assert inst._streaming_provider is adapter

    def test_dhan_instrument_has_depth200_decorator(self) -> None:
        """DhanAdapter should automatically apply Depth200Decorator."""
        adapter = _connected_dhan()
        inst = adapter.instrument("RELIANCE", "NSE")
        assert isinstance(inst, Depth200Decorator)

    def test_upstox_instrument_has_depth30_decorator(self) -> None:
        """UpstoxAdapter should automatically apply Depth30Decorator."""
        adapter = _connected_upstox()
        inst = adapter.instrument("RELIANCE", "NSE")
        assert isinstance(inst, Depth30Decorator)

    def test_paper_instrument_no_depth_decorator(self) -> None:
        """PaperAdapter should NOT apply any depth decorator."""
        adapter = PaperAdapter()
        adapter.connect()
        inst = adapter.instrument("RELIANCE", "NSE")

        from brokers_core.market.decorators import InstrumentDecorator

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
        adapter = _connected_dhan()
        adapter._market_data.quote.return_value = Quote(
            symbol="RELIANCE",
            ltp=Decimal("2500"),
        )
        adapter._market_data.depth.return_value = MarketDepth(symbol="RELIANCE")

        inst = adapter.instrument("RELIANCE", "NSE")

        quote = inst.quote()
        assert quote.ltp == Decimal("2500")

        depth = inst.depth(200)
        assert depth.symbol == "RELIANCE"

    def test_instrument_buy_delegates_to_adapter(self) -> None:
        """inst.buy() should delegate to the adapter's place_order."""
        adapter = _connected_dhan()
        adapter._orders.place_order.return_value = {
            "order_id": "ORD001",
            "success": True,
        }

        inst = adapter.instrument("RELIANCE", "NSE")
        order = inst.buy(quantity=10)

        adapter._orders.place_order.assert_called_once()
        assert order["order_id"] == "ORD001"


# ── Depth Override Tests ─────────────────────────────────────────────────


class TestDepthOverride:
    """User-specified apply_depth should override broker defaults."""

    def test_dhan_custom_apply_depth(self) -> None:
        """User can override Dhan default depth of 200."""
        adapter = _connected_dhan()
        inst = adapter.instrument("RELIANCE", "NSE", apply_depth=5)

        from brokers_core.market.decorators import InstrumentDecorator

        assert not isinstance(inst, InstrumentDecorator)

    def test_upstox_custom_apply_depth(self) -> None:
        """User can override Upstox default depth of 30."""
        adapter = _connected_upstox()
        inst = adapter.instrument("RELIANCE", "NSE", apply_depth=5)

        from brokers_core.market.decorators import InstrumentDecorator

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
        """Connecting twice should remain connected."""
        adapter = PaperAdapter()
        adapter.connect()
        adapter.connect()
        assert adapter.is_connected

    def test_dhan_quote_batch_delegates(self) -> None:
        """quote_batch should delegate to market_data.quote_batch."""
        adapter = _connected_dhan()
        adapter._market_data.quote_batch.return_value = {}

        result = adapter.quote_batch(["RELIANCE", "TCS"], "NSE")
        adapter._market_data.quote_batch.assert_called_once_with(
            ["RELIANCE", "TCS"],
            "NSE",
        )
        assert result == {}

    def test_paper_adapter_raises_on_historical(self) -> None:
        """PaperAdapter.get_candles should raise NotSupportedError."""
        import datetime

        from brokers_core.domain.exceptions import NotSupportedError

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
        """Importing adapter module should NOT load gateway at module level."""
        import importlib
        import sys

        before = {
            mod
            for mod in sys.modules
            if mod.endswith(".gateway") and "brokers_core.adapters.dhan" in mod
        }

        for mod in list(sys.modules.keys()):
            if mod.startswith("brokers_core.adapters.dhan"):
                sys.modules.pop(mod, None)

        importlib.import_module("brokers_core.adapters.dhan.adapter")

        after = {
            mod
            for mod in sys.modules
            if mod.endswith(".gateway") and "brokers_core.adapters.dhan" in mod
        }
        new_gateway_modules = after - before
        assert not new_gateway_modules, (
            f"brokers_core.adapters.dhan.adapter eagerly loaded gateway: {new_gateway_modules}"
        )


# ── DhanAdapter Depth Warning Tests ────────────────────────────────────────


class TestDhanDepthWarning:
    """DhanAdapter.depth() should accept levels parameter."""

    def test_depth_accepts_levels_parameter(self) -> None:
        """depth() accepts a levels parameter (ignored by market_data)."""
        adapter = _connected_dhan()
        adapter._market_data.depth.return_value = MarketDepth(symbol="RELIANCE")

        result = adapter.depth("RELIANCE", "NSE", levels=200)
        assert result.symbol == "RELIANCE"

    def test_depth_default_levels(self) -> None:
        """depth() with default levels parameter works."""
        adapter = _connected_dhan()
        adapter._market_data.depth.return_value = MarketDepth(symbol="RELIANCE")

        result = adapter.depth("RELIANCE", "NSE")
        assert result.symbol == "RELIANCE"
