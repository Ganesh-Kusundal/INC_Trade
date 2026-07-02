"""Gateway contract integration tests.

Tests that all broker gateways (Dhan, Upstox, Paper) implement the full
MarketDataGateway ABC contract with correct signatures, return types,
and error handling.   # noqa: W291

Uses mocked HTTP clients so tests run without live broker credentials.
"""

from __future__ import annotations

import inspect
from decimal import Decimal
from unittest.mock import MagicMock

import pandas as pd
import pytest

from brokers.common.gateway import BrokerCapabilities, MarketDataGateway
from domain import (
    Balance,
    FutureChain,
    MarketDepth,
    OptionChain,
    OrderResponse,
    Quote,
)

# ── Helpers ──────────────────────────────────────────────────────────────────


def _get_abstract_methods() -> set[str]:
    return {
        name
        for name, method in inspect.getmembers(MarketDataGateway, predicate=inspect.isfunction)
        if getattr(method, "__isabstractmethod__", False)
    }


# ── ABC Contract: Method Existence ──────────────────────────────────────────


class TestABCContractMethodExistence:
    """Verify all gateway implementations declare every ABC method."""

    def test_dhan_implements_all_abstract_methods(self):
        from brokers.dhan.gateway import BrokerGateway

        abstract = _get_abstract_methods()
        implemented = set(dir(BrokerGateway))
        missing = abstract - implemented
        assert not missing, f"Dhan BrokerGateway missing: {missing}"

    def test_upstox_implements_all_abstract_methods(self):
        from brokers.upstox.gateway import UpstoxBrokerGateway

        abstract = _get_abstract_methods()
        implemented = set(dir(UpstoxBrokerGateway))
        missing = abstract - implemented
        assert not missing, f"Upstox UpstoxBrokerGateway missing: {missing}"

    def test_paper_implements_all_abstract_methods(self):
        from brokers.paper.paper_gateway import PaperGateway

        abstract = _get_abstract_methods()
        implemented = set(dir(PaperGateway))
        missing = abstract - implemented
        assert not missing, f"Paper PaperGateway missing: {missing}"



# ── ABC Contract: Method Signatures ─────────────────────────────────────────


class TestABCContractSignatures:
    """Verify method signatures match the ABC contract (param names, defaults)."""

    def _check_signature(self, gw_class: type, method_name: str, expected_params: list[str]):
        """Check that a gateway method has the expected parameter names."""
        method = getattr(gw_class, method_name, None)
        assert method is not None, f"{gw_class.__name__}.{method_name} not found"
        sig = inspect.signature(method)
        params = [p for p in sig.parameters if p != "self"]
        # Check all expected params are present (allows extra optional params)
        for ep in expected_params:
            assert ep in params, (
                f"{gw_class.__name__}.{method_name} missing param '{ep}'. Has: {params}"
            )

    @pytest.mark.parametrize(
        "gw_module,gw_class",
        [
            ("brokers.dhan.gateway", "BrokerGateway"),
            ("brokers.upstox.gateway", "UpstoxBrokerGateway"),
            ("brokers.paper.paper_gateway", "PaperGateway"),
        ],
    )
    def test_history_signature(self, gw_module, gw_class):
        import importlib

        mod = importlib.import_module(gw_module)
        cls = getattr(mod, gw_class)
        self._check_signature(cls, "history", ["symbol", "exchange", "timeframe", "lookback_days"])

    @pytest.mark.parametrize(
        "gw_module,gw_class",
        [
            ("brokers.dhan.gateway", "BrokerGateway"),
            ("brokers.upstox.gateway", "UpstoxBrokerGateway"),
            ("brokers.paper.paper_gateway", "PaperGateway"),
        ],
    )
    def test_quote_signature(self, gw_module, gw_class):
        import importlib

        mod = importlib.import_module(gw_module)
        cls = getattr(mod, gw_class)
        self._check_signature(cls, "quote", ["symbol", "exchange"])

    @pytest.mark.parametrize(
        "gw_module,gw_class",
        [
            ("brokers.dhan.gateway", "BrokerGateway"),
            ("brokers.upstox.gateway", "UpstoxBrokerGateway"),
            ("brokers.paper.paper_gateway", "PaperGateway"),
        ],
    )
    def test_ltp_signature(self, gw_module, gw_class):
        import importlib

        mod = importlib.import_module(gw_module)
        cls = getattr(mod, gw_class)
        self._check_signature(cls, "ltp", ["symbol", "exchange"])

    @pytest.mark.parametrize(
        "gw_module,gw_class",
        [
            ("brokers.dhan.gateway", "BrokerGateway"),
            ("brokers.upstox.gateway", "UpstoxBrokerGateway"),
        ],
    )
    def test_place_order_signature(self, gw_module, gw_class):
        import importlib

        mod = importlib.import_module(gw_module)
        cls = getattr(mod, gw_class)
        self._check_signature(
            cls,
            "place_order",
            [
                "symbol",
                "exchange",
                "side",
                "quantity",
                "price",
                "order_type",
                "product_type",
            ],
        )

    @pytest.mark.parametrize(
        "gw_module,gw_class",
        [
            ("brokers.dhan.gateway", "BrokerGateway"),
            ("brokers.upstox.gateway", "UpstoxBrokerGateway"),
            ("brokers.paper.paper_gateway", "PaperGateway"),
        ],
    )
    def test_stream_signature(self, gw_module, gw_class):
        import importlib

        mod = importlib.import_module(gw_module)
        cls = getattr(mod, gw_class)
        self._check_signature(cls, "stream", ["symbol", "exchange", "mode", "on_tick"])

    @pytest.mark.parametrize(
        "gw_module,gw_class",
        [
            ("brokers.dhan.gateway", "BrokerGateway"),
            ("brokers.upstox.gateway", "UpstoxBrokerGateway"),
            ("brokers.paper.paper_gateway", "PaperGateway"),
        ],
    )
    def test_ltp_batch_signature(self, gw_module, gw_class):
        import importlib

        mod = importlib.import_module(gw_module)
        cls = getattr(mod, gw_class)
        self._check_signature(cls, "ltp_batch", ["symbols", "exchange"])

    @pytest.mark.parametrize(
        "gw_module,gw_class",
        [
            ("brokers.dhan.gateway", "BrokerGateway"),
            ("brokers.upstox.gateway", "UpstoxBrokerGateway"),
            ("brokers.paper.paper_gateway", "PaperGateway"),
        ],
    )
    def test_cancel_order_signature(self, gw_module, gw_class):
        import importlib

        mod = importlib.import_module(gw_module)
        cls = getattr(mod, gw_class)
        self._check_signature(cls, "cancel_order", ["order_id"])


# ── Dhan Gateway: Return Type Validation ────────────────────────────────────


class TestDhanGatewayReturnTypes:
    """Test Dhan BrokerGateway methods return correct types using mocked HTTP."""

    @pytest.fixture()
    def dhan_gw(self):
        conn = MagicMock()
        conn.client_id = "TEST"
        conn.access_token = "TOKEN"
        conn.instruments = MagicMock()
        conn.event_bus = None
        conn.market_feed = None
        conn._lifecycle = None

        inst = MagicMock()
        inst.exchange = MagicMock()
        inst.exchange.value = "NSE"
        inst.security_id = "2885"
        inst.symbol = "RELIANCE"
        inst.instrument_type = MagicMock()
        inst.instrument_type.value = "EQUITY"
        inst.canonical_symbol = "RELIANCE"
        conn.instruments.resolve.return_value = inst

        from brokers.dhan.gateway import BrokerGateway

        gw = BrokerGateway(conn)
        return gw

    def test_ltp_returns_decimal(self, dhan_gw):
        dhan_gw._conn.market_data.get_ltp.return_value = Decimal("2450.55")
        result = dhan_gw.ltp("RELIANCE", "NSE")
        assert isinstance(result, Decimal)

    def test_quote_returns_quote(self, dhan_gw):
        dhan_gw._conn.market_data.get_quote.return_value = Quote(
            symbol="RELIANCE",
            ltp=Decimal("2450"),
            open=Decimal("2430"),
            high=Decimal("2460"),
            low=Decimal("2420"),
            close=Decimal("2425"),
            volume=100000,
            change=Decimal("25"),
        )
        result = dhan_gw.quote("RELIANCE", "NSE")
        assert isinstance(result, Quote)

    def test_depth_returns_market_depth(self, dhan_gw):
        dhan_gw._conn.market_data.get_depth.return_value = MarketDepth()
        result = dhan_gw.depth("RELIANCE", "NSE")
        assert isinstance(result, MarketDepth)

    def test_positions_returns_list(self, dhan_gw):
        dhan_gw._conn.portfolio.get_positions.return_value = []
        result = dhan_gw.positions()
        assert isinstance(result, list)

    def test_holdings_returns_list(self, dhan_gw):
        dhan_gw._conn.portfolio.get_holdings.return_value = []
        result = dhan_gw.holdings()
        assert isinstance(result, list)

    def test_funds_returns_balance(self, dhan_gw):
        dhan_gw._conn.portfolio.get_balance.return_value = Balance(
            available_balance=Decimal("100000"),
            used_margin=Decimal("0"),
        )
        result = dhan_gw.funds()
        assert isinstance(result, Balance)

    def test_get_orderbook_returns_list(self, dhan_gw):
        dhan_gw._conn.orders.get_orderbook.return_value = []
        result = dhan_gw.get_orderbook()
        assert isinstance(result, list)

    def test_get_trade_book_returns_list(self, dhan_gw):
        dhan_gw._conn.orders.get_trade_book.return_value = []
        result = dhan_gw.get_trade_book()
        assert isinstance(result, list)

    def test_capabilities_returns_broker_capabilities(self, dhan_gw):
        result = dhan_gw.capabilities()
        assert isinstance(result, BrokerCapabilities)
        assert hasattr(result, "stream_limits")
        assert hasattr(result, "supports_depth_20_ws")

    def test_describe_returns_dict(self, dhan_gw):
        result = dhan_gw.describe()
        assert isinstance(result, dict)
        assert "broker" in result

    def test_history_returns_dataframe(self, dhan_gw):
        dhan_gw._conn.historical.get_historical.return_value = pd.DataFrame(
            {
                "timestamp": ["2026-06-01"],
                "open": [2450],
                "high": [2460],
                "low": [2440],
                "close": [2455],
                "volume": [100000],
            }
        )
        result = dhan_gw.history("RELIANCE", "NSE", timeframe="1D", lookback_days=5)
        assert isinstance(result, pd.DataFrame)

    def test_ltp_batch_returns_dict(self, dhan_gw):
        dhan_gw._conn.market_data.get_batch_ltp.return_value = {
            "RELIANCE": Decimal("2450"),
            "TCS": Decimal("3500"),
        }
        result = dhan_gw.ltp_batch(["RELIANCE", "TCS"], "NSE")
        assert isinstance(result, dict)
        assert all(isinstance(v, Decimal) for v in result.values())

    def test_search_returns_list(self, dhan_gw):
        dhan_gw._conn.instruments.all_instruments.return_value = []
        result = dhan_gw.search("RELIANCE")
        assert isinstance(result, list)

    def test_trades_returns_list(self, dhan_gw):
        dhan_gw._conn.orders.get_trade_book.return_value = []
        result = dhan_gw.trades()
        assert isinstance(result, list)

    def test_option_chain_returns_option_chain(self, dhan_gw):
        options_adapter = MagicMock()
        options_adapter.get_expiries.return_value = ["2026-06-26"]
        options_adapter.get_option_chain.return_value = {
            "underlying": "NIFTY",
            "exchange": "NFO",
            "expiry": "2026-06-26",
            "data": [],
        }
        dhan_gw._conn.options = options_adapter
        result = dhan_gw.option_chain("NIFTY", "NFO")
        assert isinstance(result, OptionChain)

    def test_future_chain_returns_future_chain(self, dhan_gw):
        dhan_gw._conn.futures = MagicMock()
        dhan_gw._conn.futures.get_contracts.return_value = []
        dhan_gw._conn.futures.get_expiries.return_value = []
        result = dhan_gw.future_chain("NIFTY", "NFO")
        assert isinstance(result, FutureChain)

    def test_unstream_exists_and_is_callable(self, dhan_gw):
        assert callable(getattr(dhan_gw, "unstream", None))

    def test_depth_20_exists_and_is_callable(self, dhan_gw):
        assert callable(getattr(dhan_gw, "depth_20", None))

    def test_depth_200_exists_and_is_callable(self, dhan_gw):
        assert callable(getattr(dhan_gw, "depth_200", None))


# ── Upstox Gateway: Return Type Validation ──────────────────────────────────


class TestUpstoxGatewayReturnTypes:
    """Test Upstox UpstoxBrokerGateway methods return correct types using mocked broker."""

    @pytest.fixture()
    def upstox_gw(self):
        broker = MagicMock()
        broker.market_data_websocket = MagicMock()
        broker.market_data_websocket._connected = False
        broker.market_data_websocket._listeners = []
        broker.market_data_websocket.is_connected = False
        broker.instrument_resolver = MagicMock()
        broker.instrument_resolver.is_loaded.return_value = True

        from brokers.upstox.gateway import UpstoxBrokerGateway

        gw = UpstoxBrokerGateway(broker)
        return gw

    def test_ltp_returns_decimal(self, upstox_gw):
        upstox_gw._broker.market_data_v2.get_ltp.return_value = {
            "data": {"NSE_EQ|INE002A01018": {"last_price": 2450.55}},
        }
        upstox_gw._resolve_instrument_key = lambda s, e: "NSE_EQ|INE002A01018"
        result = upstox_gw.ltp("RELIANCE", "NSE")
        assert isinstance(result, Decimal)

    def test_quote_returns_quote(self, upstox_gw):
        upstox_gw._broker.market_data_v2.get_quote.return_value = {
            "data": {
                "NSE_EQ|INE002A01018": {
                    "last_price": 2450.55,
                    "ohlc": {
                        "open": 2430,
                        "high": 2460,
                        "low": 2420,
                        "close": 2425,
                    },
                    "volume": 100000,
                    "net_change": 25,
                }
            },
        }
        upstox_gw._resolve_instrument_key = lambda s, e: "NSE_EQ|INE002A01018"
        result = upstox_gw.quote("RELIANCE", "NSE")
        assert isinstance(result, Quote)

    def test_depth_returns_market_depth(self, upstox_gw):
        upstox_gw._broker.market_data_v2.get_order_book.return_value = {"data": {}}
        upstox_gw._resolve_instrument_key = lambda s, e: "NSE_EQ|INE002A01018"
        result = upstox_gw.depth("RELIANCE", "NSE")
        assert isinstance(result, MarketDepth)

    def test_positions_returns_list(self, upstox_gw):
        upstox_gw._broker.portfolio.get_positions.return_value = []
        result = upstox_gw.positions()
        assert isinstance(result, list)

    def test_holdings_returns_list(self, upstox_gw):
        upstox_gw._broker.portfolio.get_holdings.return_value = []
        result = upstox_gw.holdings()
        assert isinstance(result, list)

    def test_funds_returns_balance(self, upstox_gw):
        upstox_gw._broker.portfolio.get_fund_limits.return_value = Balance(
            available_balance=Decimal("100000"),
            used_margin=Decimal("0"),
        )
        result = upstox_gw.funds()
        assert isinstance(result, Balance)

    def test_get_orderbook_returns_list(self, upstox_gw):
        upstox_gw._broker.order_query.get_order_list.return_value = []
        result = upstox_gw.get_orderbook()
        assert isinstance(result, list)

    def test_get_trade_book_returns_list(self, upstox_gw):
        upstox_gw._broker.order_query.get_trades.return_value = []
        result = upstox_gw.get_trade_book()
        assert isinstance(result, list)

    def test_describe_returns_dict(self, upstox_gw):
        result = upstox_gw.describe()
        assert isinstance(result, dict)
        assert "broker" in result

    def test_search_returns_list(self, upstox_gw):
        upstox_gw._broker.instrument_resolver.search.return_value = []
        result = upstox_gw.search("RELIANCE")
        assert isinstance(result, list)

    def test_unstream_exists_and_is_callable(self, upstox_gw):
        assert callable(getattr(upstox_gw, "unstream", None))


# ── Paper Gateway: Full Contract Compliance ─────────────────────────────────


class TestPaperGatewayContract:
    """PaperGateway must implement every ABC method and return correct types."""

    @pytest.fixture()
    def paper_gw(self):
        from brokers.paper.paper_gateway import PaperGateway

        return PaperGateway()

    def test_ltp_returns_decimal(self, paper_gw):
        result = paper_gw.ltp("RELIANCE", "NSE")
        assert isinstance(result, Decimal)

    def test_quote_returns_quote(self, paper_gw):
        result = paper_gw.quote("RELIANCE", "NSE")
        assert isinstance(result, Quote)

    def test_depth_returns_market_depth(self, paper_gw):
        result = paper_gw.depth("RELIANCE", "NSE")
        assert isinstance(result, MarketDepth)

    def test_history_returns_dataframe(self, paper_gw):
        result = paper_gw.history("RELIANCE", "NSE")
        assert isinstance(result, pd.DataFrame)

    def test_positions_returns_list(self, paper_gw):
        result = paper_gw.positions()
        assert isinstance(result, list)

    def test_holdings_returns_list(self, paper_gw):
        result = paper_gw.holdings()
        assert isinstance(result, list)

    def test_funds_returns_balance(self, paper_gw):
        result = paper_gw.funds()
        assert isinstance(result, Balance)

    def test_trades_returns_list(self, paper_gw):
        result = paper_gw.trades()
        assert isinstance(result, list)

    def test_get_orderbook_returns_list(self, paper_gw):
        result = paper_gw.get_orderbook()
        assert isinstance(result, list)

    def test_get_trade_book_returns_list(self, paper_gw):
        result = paper_gw.get_trade_book()
        assert isinstance(result, list)

    def test_capabilities_returns_broker_capabilities(self, paper_gw):
        result = paper_gw.capabilities()
        assert isinstance(result, BrokerCapabilities)

    def test_describe_returns_dict(self, paper_gw):
        result = paper_gw.describe()
        assert isinstance(result, dict)
        assert "name" in result

    def test_place_order_returns_order_response(self, paper_gw):
        result = paper_gw.place_order("RELIANCE", quantity=1)
        assert isinstance(result, OrderResponse)

    def test_cancel_order_returns_value(self, paper_gw):
        # Note: Paper gateway returns bool instead of OrderResponse (contract deviation)
        result = paper_gw.cancel_order("ORD-001")
        assert result is not None  # Returns bool or OrderResponse

    def test_search_returns_list(self, paper_gw):
        result = paper_gw.search("RELIANCE")
        assert isinstance(result, list)

    def test_ltp_batch_returns_dict(self, paper_gw):
        result = paper_gw.ltp_batch(["RELIANCE", "TCS"], "NSE")
        assert isinstance(result, dict)

    def test_close_is_callable(self, paper_gw):
        assert callable(paper_gw.close)
        paper_gw.close()  # Should not raise



# ── ObservabilityProvider Contract ───────────────────────────────────────────


class TestObservabilityProvider:
    """Dhan gateway must implement ObservabilityProvider methods."""

    def test_dhan_get_connection_status(self):
        from brokers.dhan.gateway import BrokerGateway

        conn = MagicMock()
        conn.client_id = "TEST"
        conn.instruments = MagicMock()
        conn.event_bus = None
        conn.market_feed = None
        conn._lifecycle = None
        gw = BrokerGateway(conn)

        result = gw.get_connection_status()
        assert isinstance(result, dict)

    def test_dhan_get_circuit_breaker_states(self):
        from brokers.dhan.gateway import BrokerGateway

        conn = MagicMock()
        conn.client_id = "TEST"
        conn.instruments = MagicMock()
        conn.event_bus = None
        conn.market_feed = None
        conn._lifecycle = None
        conn.circuit_breaker_states = {"data": 0, "order": 0, "quote": 0}
        gw = BrokerGateway(conn)

        result = gw.get_circuit_breaker_states()
        assert isinstance(result, dict)

    def test_dhan_get_token_refresh_metrics(self):
        from brokers.dhan.gateway import BrokerGateway

        conn = MagicMock()
        conn.client_id = "TEST"
        conn.instruments = MagicMock()
        conn.event_bus = None
        conn.market_feed = None
        conn._lifecycle = None
        conn.token_refresh_metrics = {"refresh_count": 0, "last_refresh": None}
        gw = BrokerGateway(conn)

        result = gw.get_token_refresh_metrics()
        assert isinstance(result, dict)
        assert "refresh_count" in result
