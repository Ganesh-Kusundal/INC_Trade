"""Tests for BrokerSession — the single entry point for broker connections."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from inc_trade.market.session import BrokerSession


@pytest.fixture
def mock_adapter() -> MagicMock:
    """Create a mock broker adapter."""
    adapter = MagicMock()
    adapter.broker_id = "mock"
    adapter.is_connected = False
    adapter.connect = MagicMock()
    adapter.disconnect = MagicMock()
    adapter.quote.return_value = {"symbol": "RELIANCE", "ltp": 2850.50}
    adapter.ltp.return_value = Decimal("2850.50")
    adapter.depth.return_value = {"bids": [], "asks": []}
    adapter.place_order.return_value = {"order_id": "12345", "status": "PENDING"}
    return adapter


class TestBrokerSession:
    """Tests for BrokerSession lifecycle and instrument access."""

    def test_create_session(self, mock_adapter: MagicMock) -> None:
        session = BrokerSession(mock_adapter)
        assert session.adapter is mock_adapter
        assert not session.is_connected

    def test_connect_disconnect(self, mock_adapter: MagicMock) -> None:
        import asyncio

        session = BrokerSession(mock_adapter)
        asyncio.run(session.connect())
        mock_adapter.connect.assert_called_once()
        asyncio.run(session.disconnect())
        mock_adapter.disconnect.assert_called_once()

    def test_connect_is_coroutine(self, mock_adapter: MagicMock) -> None:
        """Session connect/disconnect should be awaitable."""
        import inspect

        session = BrokerSession(mock_adapter)
        assert inspect.iscoroutinefunction(session.connect)
        assert inspect.iscoroutinefunction(session.disconnect)

    def test_equity_returns_instrument(self, mock_adapter: MagicMock) -> None:
        session = BrokerSession(mock_adapter)
        inst = session.equity("RELIANCE", "NSE")
        assert inst.symbol == "RELIANCE"
        assert inst.exchange == "NSE"
        assert inst.is_equity()

    def test_equity_identity_guarantee(self, mock_adapter: MagicMock) -> None:
        session = BrokerSession(mock_adapter)
        inst1 = session.equity("RELIANCE", "NSE")
        inst2 = session.equity("RELIANCE", "NSE")
        assert inst1 is inst2  # Same object (identity guarantee)

    def test_future_returns_instrument(self, mock_adapter: MagicMock) -> None:
        session = BrokerSession(mock_adapter)
        expiry = datetime(2025, 6, 26)
        inst = session.future("NIFTY", expiry)
        assert inst.symbol == "NIFTY"
        assert inst.exchange == "NFO"
        assert inst.expiry == expiry
        assert inst.is_future()

    def test_future_identity_guarantee(self, mock_adapter: MagicMock) -> None:
        session = BrokerSession(mock_adapter)
        expiry = datetime(2025, 6, 26)
        inst1 = session.future("NIFTY", expiry)
        inst2 = session.future("NIFTY", expiry)
        assert inst1 is inst2

    def test_option_returns_instrument(self, mock_adapter: MagicMock) -> None:
        session = BrokerSession(mock_adapter)
        expiry = datetime(2025, 6, 26)
        inst = session.option("NIFTY", expiry, Decimal("25000"), "CE")
        assert inst.symbol == "NIFTY"
        assert inst.exchange == "NFO"
        assert inst.strike == Decimal("25000")
        assert inst.option_type == "CE"
        assert inst.is_option()

    def test_option_identity_guarantee(self, mock_adapter: MagicMock) -> None:
        session = BrokerSession(mock_adapter)
        expiry = datetime(2025, 6, 26)
        inst1 = session.option("NIFTY", expiry, Decimal("25000"), "CE")
        inst2 = session.option("NIFTY", expiry, Decimal("25000"), "CE")
        assert inst1 is inst2

    def test_different_options_different_identity(self, mock_adapter: MagicMock) -> None:
        session = BrokerSession(mock_adapter)
        expiry = datetime(2025, 6, 26)
        ce = session.option("NIFTY", expiry, Decimal("25000"), "CE")
        pe = session.option("NIFTY", expiry, Decimal("25000"), "PE")
        assert ce is not pe  # Different option_type → different identity

    def test_query_returns_market_data_query(self, mock_adapter: MagicMock) -> None:
        session = BrokerSession(mock_adapter)
        inst = session.equity("RELIANCE")
        query = session.query(inst)
        assert query.instrument is inst

    def test_query_delegates_quote_to_adapter(self, mock_adapter: MagicMock) -> None:
        session = BrokerSession(mock_adapter)
        inst = session.equity("RELIANCE")
        query = session.query(inst)
        result = query.quote()
        mock_adapter.quote.assert_called_once_with("RELIANCE", "NSE")
        assert result == {"symbol": "RELIANCE", "ltp": 2850.50}

    def test_query_ltp(self, mock_adapter: MagicMock) -> None:
        session = BrokerSession(mock_adapter)
        inst = session.equity("RELIANCE")
        query = session.query(inst)
        result = query.ltp()
        assert result == Decimal("2850.50")

    def test_command_returns_order_command(self, mock_adapter: MagicMock) -> None:
        session = BrokerSession(mock_adapter)
        inst = session.equity("RELIANCE")
        cmd = session.command(inst)
        assert cmd.instrument is inst

    def test_command_buy(self, mock_adapter: MagicMock) -> None:
        session = BrokerSession(mock_adapter)
        inst = session.equity("RELIANCE")
        cmd = session.command(inst)
        result = cmd.buy(quantity=10)
        mock_adapter.place_order.assert_called_once()
        assert result == {"order_id": "12345", "status": "PENDING"}

    def test_command_sell(self, mock_adapter: MagicMock) -> None:
        session = BrokerSession(mock_adapter)
        inst = session.equity("RELIANCE")
        cmd = session.command(inst)
        result = cmd.sell(quantity=5)
        mock_adapter.place_order.assert_called_once()
        assert result == {"order_id": "12345", "status": "PENDING"}

    def test_search(self, mock_adapter: MagicMock) -> None:
        session = BrokerSession(mock_adapter)
        session.equity("RELIANCE", "NSE")
        session.equity("NIFTY", "NSE")
        results = session.search("REL")
        assert len(results) == 1
        assert results[0].symbol == "RELIANCE"

    def test_instruments_snapshot(self, mock_adapter: MagicMock) -> None:
        session = BrokerSession(mock_adapter)
        session.equity("RELIANCE", "NSE")
        session.equity("NIFTY", "NSE")
        all_inst = session.instruments()
        assert len(all_inst) == 2
        assert "NSE:RELIANCE" in all_inst
        assert "NSE:NIFTY" in all_inst

    def test_event_bus_available(self, mock_adapter: MagicMock) -> None:
        session = BrokerSession(mock_adapter)
        assert session.event_bus is not None
        # Event bus should have pub/sub
        assert hasattr(session.event_bus, "publish")
        assert hasattr(session.event_bus, "subscribe")

    def test_repr(self, mock_adapter: MagicMock) -> None:
        session = BrokerSession(mock_adapter)
        session.equity("RELIANCE")
        assert "BrokerSession" in repr(session)
        assert "mock" in repr(session)

    def test_clear_on_disconnect(self, mock_adapter: MagicMock) -> None:
        import asyncio

        session = BrokerSession(mock_adapter)
        session.equity("RELIANCE")
        assert len(session.instruments()) == 1
        asyncio.run(session.disconnect())
        assert len(session.instruments()) == 0  # Registry cleared

    def test_async_adapter(self) -> None:
        """Test session with an async adapter."""
        import asyncio

        class AsyncAdapter:
            """A proper async adapter with coroutine connect/disconnect."""

            broker_id = "async_mock"
            is_connected = False

            async def connect(self) -> None:
                self.is_connected = True

            async def disconnect(self) -> None:
                self.is_connected = False

            def quote(self, symbol: str, exchange: str) -> dict:
                return {"ltp": 100.0, "symbol": symbol}

            def ltp(self, symbol: str, exchange: str) -> Decimal:
                return Decimal("100.0")

        adapter = AsyncAdapter()
        session = BrokerSession(adapter)

        # Initially not connected
        assert not session.is_connected

        # Async connect should work
        asyncio.run(session.connect())
        assert adapter.is_connected

        # Async disconnect should work
        asyncio.run(session.disconnect())
        assert not adapter.is_connected
