"""Integration tests: BrokerSession + PaperAdapter.

Verifies that the new PaperAdapter works correctly with the
BrokerSession/MarketDataQuery/OrderCommand infrastructure.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from brokers.adapters.paper.adapter import PaperAdapter


@pytest.fixture
def adapter() -> PaperAdapter:
    a = PaperAdapter()
    a.connect()
    return a


class TestSessionIntegration:
    """BrokerSession + PaperAdapter integration."""

    def test_session_connect_disconnect(self, adapter: PaperAdapter) -> None:
        """BrokerSession connects and disconnects with PaperAdapter."""
        from inc_trade.market.session import BrokerSession

        session = BrokerSession(adapter)

        async def run() -> None:
            await session.connect()
            assert session.is_connected

            await session.disconnect()
            assert not session.is_connected

        asyncio.run(run())

    def test_session_equity_instrument(self, adapter: PaperAdapter) -> None:
        """BrokerSession.equity() returns an Instrument."""
        from inc_trade.market.session import BrokerSession

        session = BrokerSession(adapter)

        async def run() -> None:
            await session.connect()

            rel = session.equity("RELIANCE")
            assert rel.symbol == "RELIANCE"
            assert rel.exchange == "NSE"
            assert rel.is_equity()

        asyncio.run(run())

    def test_session_query_ltp(self, adapter: PaperAdapter) -> None:
        """BrokerSession.query().ltp() works."""
        from inc_trade.market.session import BrokerSession

        session = BrokerSession(adapter)

        async def run() -> None:
            await session.connect()

            rel = session.equity("RELIANCE")
            query = session.query(rel)
            ltp = query.ltp()
            assert ltp == Decimal("100.00")  # default paper LTP

        asyncio.run(run())

    def test_session_command_place_order(self, adapter: PaperAdapter) -> None:
        """BrokerSession.command().buy() works."""
        from inc_trade.market.session import BrokerSession

        session = BrokerSession(adapter)

        async def run() -> None:
            await session.connect()

            rel = session.equity("RELIANCE")
            cmd = session.command(rel)
            response = cmd.buy(quantity=10)
            assert response.success
            assert response.order_id.startswith("PAPER-")

        asyncio.run(run())

    def test_session_quote_via_adapter(self, adapter: PaperAdapter) -> None:
        """Quote set via adapter is reflected in session.query."""
        from inc_trade.market.session import BrokerSession

        session = BrokerSession(adapter)

        async def run() -> None:
            await session.connect()

            # Set quote AFTER connecting (connect reinitialises sub-adapters)
            adapter.set_quote("RELIANCE", Decimal("2850.50"))

            rel = session.equity("RELIANCE")
            query = session.query(rel)
            ltp = query.ltp()
            assert ltp == Decimal("2850.50")

        asyncio.run(run())

    def test_instrument_identity_same_symbol(self, adapter: PaperAdapter) -> None:
        """Same symbol returns same Instrument object."""
        from inc_trade.market.session import BrokerSession

        session = BrokerSession(adapter)

        async def run() -> None:
            await session.connect()

            rel1 = session.equity("RELIANCE")
            rel2 = session.equity("RELIANCE")
            assert rel1 is rel2  # same identity

            nifty = session.future(
                "NIFTY",
                expiry=__import__("datetime").datetime(2025, 6, 26),
            )
            nifty2 = session.future(
                "NIFTY",
                expiry=__import__("datetime").datetime(2025, 6, 26),
            )
            assert nifty is nifty2  # same identity

        asyncio.run(run())

    def test_session_search(self, adapter: PaperAdapter) -> None:
        """BrokerSession.search() works."""
        from inc_trade.market.session import BrokerSession

        session = BrokerSession(adapter)

        async def run() -> None:
            await session.connect()

            session.equity("RELIANCE")
            session.equity("TCS")

            results = session.search("REL")
            assert len(results) == 1
            assert results[0].symbol == "RELIANCE"

            results = session.search("TCS")
            assert len(results) == 1

        asyncio.run(run())
