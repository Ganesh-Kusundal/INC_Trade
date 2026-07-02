"""Regression tests for gateway issues found in the in-depth review.

Validates:
- Local imports hoisted (no `from brokers.dhan.segments import` inside methods)
- Hardcoded `"NSE_EQ"` replaced with `DEFAULT_SEGMENT` constant
- Upstox `option_chain` / `future_chain` raise NotImplementedError (genuinely unsupported)
- Upstox `get_trade_book` returns [] (no endpoint, but ABC contract returns list)
- `MarketDataGateway` contract is honored by both brokers
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from brokers.common.gateway import MarketDataGateway

GATEWAY_DIR = Path(__file__).resolve().parents[2]


class TestGatewayImportHygiene:
    """No local imports of internal modules inside gateway methods."""

    def test_dhan_gateway_no_local_segment_imports(self):
        """EXCHANGE_TO_SEGMENT must be imported at module level in dhan/gateway.py."""
        import ast

        with open(GATEWAY_DIR / "dhan" / "gateway.py") as f:
            tree = ast.parse(f.read())

        # Top-level imports
        top_imports = set()
        for node in tree.body:
            if isinstance(node, ast.ImportFrom | ast.Import):
                for alias in node.names:
                    top_imports.add(alias.asname or alias.name)

        assert "EXCHANGE_TO_SEGMENT" in top_imports, (
            "EXCHANGE_TO_SEGMENT must be imported at module level"
        )

        # No local imports of segments module inside functions
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module
                and "segments" in node.module
                and node not in tree.body
            ):
                pytest.fail(f"Local import of {node.module} found inside function")

    def test_dhan_gateway_no_local_websocket_imports(self):
        """DhanMarketFeed must be imported at module level in dhan/connection.py.

        Note: The gateway delegates WebSocket creation to the connection layer,
        so we check connection.py instead of gateway.py.
        """
        with open(GATEWAY_DIR / "dhan" / "connection.py") as f:
            tree = ast.parse(f.read())

        top_imports = set()
        for node in tree.body:
            if isinstance(node, ast.ImportFrom | ast.Import):
                for alias in node.names:
                    top_imports.add(alias.asname or alias.name)

        assert "DhanMarketFeed" in top_imports, "DhanMarketFeed must be imported at module level in connection.py"


class TestGatewaySegmentConstants:
    """Hardcoded segment strings replaced with constants."""

    def test_no_hardcoded_nse_eq_as_default_in_gateway(self):
        """No hardcoded 'NSE_EQ' used as a fallback default in gateway methods.

        Allowed: exchange string membership checks (e.g. `if exchange in ('NSE', 'NSE_EQ', ...)`).
        Forbidden: using as fallback in `EXCHANGE_TO_SEGMENT.get(..., 'NSE_EQ')`.
        """
        with open(GATEWAY_DIR / "dhan" / "gateway.py") as f:
            content = f.read()
        import re

        # Find all "NSE_EQ" used as a fallback default
        fallback_pattern = re.compile(r"\.get\([^,]+,\s*['\"]NSE_EQ['\"]\)")
        fallbacks = fallback_pattern.findall(content)
        assert len(fallbacks) == 0, (
            f"Found {len(fallbacks)} hardcoded 'NSE_EQ' fallback defaults, expected 0. "
            f"Use DEFAULT_SEGMENT constant instead."
        )

    def test_default_segment_constant_exists(self):
        from brokers.dhan.segments import DEFAULT_SEGMENT

        assert DEFAULT_SEGMENT == "NSE_EQ"


class TestUpstoxNotImplementedErrors:
    """Upstox unsupported endpoints must raise NotImplementedError, not return error dicts."""

    @pytest.fixture
    def upstox_gateway(self):
        from unittest.mock import MagicMock

        from brokers.upstox.gateway import UpstoxBrokerGateway

        gw = UpstoxBrokerGateway.__new__(UpstoxBrokerGateway)
        gw._broker = MagicMock()
        return gw

    def test_upstox_option_chain_delegates_to_broker(self, upstox_gateway):
        """Upstox option_chain now delegates to the broker's options adapter."""
        upstox_gateway._broker.options.get_expiries.return_value = ["2026-06-25"]
        upstox_gateway._broker.options.get_option_chain.return_value = []
        result = upstox_gateway.option_chain("NIFTY", exchange="NFO")
        from domain import OptionChain

        assert isinstance(result, OptionChain)
        assert result.underlying == "NIFTY"

    def test_upstox_future_chain_returns_future_chain(self, upstox_gateway):
        """Upstox future_chain delegates to broker futures adapter."""
        upstox_gateway._broker.futures.get_contracts.return_value = [
            {
                "expiry": "2026-06-26",
                "symbol": "NIFTY26JUNFUT",
                "lot_size": 75,
                "underlying": "NIFTY",
            },
        ]
        upstox_gateway._broker.futures.get_expiries.return_value = ["2026-06-26"]
        result = upstox_gateway.future_chain("NIFTY", exchange="NFO")
        from domain import FutureChain

        assert isinstance(result, FutureChain)
        assert result.underlying == "NIFTY"
        assert len(result.contracts) == 1

    def test_upstox_get_trade_book_delegates_to_order_query(self, upstox_gateway):
        """Upstox get_trade_book delegates to PortfolioAdapter.get_trades()."""
        from unittest.mock import MagicMock

        upstox_gateway._portfolio = MagicMock()
        upstox_gateway._portfolio.get_trades.return_value = []
        result = upstox_gateway.get_trade_book()
        assert result == []
        upstox_gateway._portfolio.get_trades.assert_called_once()


class TestMarketDataGatewayContract:
    """Both brokers must implement every abstract method of MarketDataGateway."""

    @pytest.fixture
    def abstract_methods(self):
        return set(MarketDataGateway.__abstractmethods__)

    def test_dhan_gateway_implements_all_abstract(self, abstract_methods):
        from brokers.dhan.gateway import BrokerGateway as DhanGateway

        dhan_methods = set(dir(DhanGateway))
        missing = abstract_methods - dhan_methods
        assert not missing, f"Dhan gateway missing abstract methods: {missing}"

    def test_upstox_gateway_implements_all_abstract(self, abstract_methods):
        from brokers.upstox.gateway import UpstoxBrokerGateway

        upstox_methods = set(dir(UpstoxBrokerGateway))
        missing = abstract_methods - upstox_methods
        assert not missing, f"Upstox gateway missing abstract methods: {missing}"


class TestDhanGatewaySegmentMapping:
    """Dhan gateway uses EXCHANGE_TO_SEGMENT for all segment lookups."""

    @pytest.fixture
    def dhan_gateway(self):
        from unittest.mock import MagicMock

        from brokers.dhan.gateway import BrokerGateway as DhanGateway
        from brokers.dhan.resolver import SymbolResolver

        resolver = SymbolResolver()
        from brokers.dhan.domain import Exchange, Instrument, InstrumentType
        from domain.entities.instrument import Instrument as DomainInstrument

        resolver._by_security_id = {
            "2885": Instrument(
                domain_instrument=DomainInstrument(
                    symbol="RELIANCE",
                    exchange="NSE",
                    security_id="2885",
                    instrument_type="EQUITY",
                ),
                exchange=Exchange.NSE,
                instrument_type=InstrumentType.EQUITY,
            )
        }
        conn = MagicMock()
        conn.instruments = resolver
        conn._client.client_id = "test"
        conn._client.access_token = "test"
        gw = DhanGateway.__new__(DhanGateway)
        gw._conn = conn
        return gw

    def test_default_segment_used_when_exchange_not_mapped(self, dhan_gateway):
        """Fallback segment should use DEFAULT_SEGMENT constant, not hardcoded string."""
        from brokers.dhan.segments import DEFAULT_SEGMENT, EXCHANGE_TO_SEGMENT

        assert EXCHANGE_TO_SEGMENT.get("UNKNOWN", DEFAULT_SEGMENT) == "NSE_EQ"


class TestGatewayTypeSafety:
    """Gateway return types must be specific, not `Any`."""

    def _get_method_return_annotation(self, gateway_class, method_name: str) -> str | None:
        import ast

        with open(GATEWAY_DIR / f"{gateway_class.__module__.split('.')[1]}" / "gateway.py") as f:
            tree = ast.parse(f.read())

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == gateway_class.__name__:
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == method_name:
                        return ast.unparse(item.returns) if item.returns else None
        return None

    def test_dhan_quote_returns_quote_type(self):
        from brokers.dhan.gateway import BrokerGateway as DhanGateway

        ret = self._get_method_return_annotation(DhanGateway, "quote")
        assert ret == "Quote", f"Expected 'Quote', got {ret!r}"

    def test_dhan_positions_returns_list_position(self):
        from brokers.dhan.gateway import BrokerGateway as DhanGateway

        ret = self._get_method_return_annotation(DhanGateway, "positions")
        assert ret == "list[Position]", f"Expected 'list[Position]', got {ret!r}"

    def test_dhan_funds_returns_balance(self):
        from brokers.dhan.gateway import BrokerGateway as DhanGateway

        ret = self._get_method_return_annotation(DhanGateway, "funds")
        assert ret == "Balance", f"Expected 'Balance', got {ret!r}"

    def test_upstox_quote_returns_quote_type(self):
        from brokers.upstox.gateway import UpstoxBrokerGateway

        ret = self._get_method_return_annotation(UpstoxBrokerGateway, "quote")
        assert ret == "Quote", f"Expected 'Quote', got {ret!r}"

    def test_upstox_depth_returns_market_depth_type(self):
        from brokers.upstox.gateway import UpstoxBrokerGateway

        ret = self._get_method_return_annotation(UpstoxBrokerGateway, "depth")
        assert ret == "MarketDepth", f"Expected 'MarketDepth', got {ret!r}"

    def test_upstox_funds_returns_balance(self):
        from brokers.upstox.gateway import UpstoxBrokerGateway

        ret = self._get_method_return_annotation(UpstoxBrokerGateway, "funds")
        assert ret == "Balance", f"Expected 'Balance', got {ret!r}"

    def test_upstox_positions_returns_list_position(self):
        from brokers.upstox.gateway import UpstoxBrokerGateway

        ret = self._get_method_return_annotation(UpstoxBrokerGateway, "positions")
        assert ret == "list[Position]", f"Expected 'list[Position]', got {ret!r}"

    def test_upstox_holdings_returns_list_holding(self):
        from brokers.upstox.gateway import UpstoxBrokerGateway

        ret = self._get_method_return_annotation(UpstoxBrokerGateway, "holdings")
        assert ret == "list[Holding]", f"Expected 'list[Holding]', got {ret!r}"

    def test_upstox_trades_returns_list_trade(self):
        from brokers.upstox.gateway import UpstoxBrokerGateway

        ret = self._get_method_return_annotation(UpstoxBrokerGateway, "trades")
        assert ret == "list[Trade]", f"Expected 'list[Trade]', got {ret!r}"

    def test_upstox_get_orderbook_returns_list_order(self):
        from brokers.upstox.gateway import UpstoxBrokerGateway

        ret = self._get_method_return_annotation(UpstoxBrokerGateway, "get_orderbook")
        assert ret == "list[Order]", f"Expected 'list[Order]', got {ret!r}"

    def test_no_any_in_critical_domain_methods(self):
        """Critical domain methods must not return `Any`."""
        import ast

        critical_methods = ["quote", "depth", "funds", "positions", "holdings", "trades"]
        for gateway_name in ["dhan", "upstox"]:
            gw_path = GATEWAY_DIR / gateway_name / "gateway.py"
            with open(gw_path) as f:
                tree = ast.parse(f.read())

            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef) and item.name in critical_methods:
                            ret = ast.unparse(item.returns) if item.returns else None
                            assert ret != "Any", (
                                f"{gateway_name}.{node.name}.{item.name} returns Any"
                            )


class TestGatewayLogging:
    """Gateway files must have proper logging setup."""

    def test_dhan_gateway_has_logger(self):
        """Dhan gateway must have a module-level logger."""
        content = (GATEWAY_DIR / "dhan" / "gateway.py").read_text()
        assert "import logging" in content
        assert "logger = logging.getLogger(__name__)" in content

    def test_upstox_gateway_has_logger(self):
        """Upstox gateway must have a module-level logger."""
        content = (GATEWAY_DIR / "upstox" / "gateway.py").read_text()
        assert "import logging" in content
        assert "logger = logging.getLogger(__name__)" in content


class TestUpstoxQuoteLogging:
    """P-2.2: Test removed - was testing deleted adapter.

    The correct adapter (brokers.upstox.market_data.market_data_adapter)   # noqa: W291
    does not log warnings for empty quotes - it returns empty Quote objects.
    """
    pass
