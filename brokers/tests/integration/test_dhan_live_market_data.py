"""Integration tests for Dhan provider — VCR.py cassette replay.

Uses the VCR.py cassette framework defined in ``brokers/tests/conftest.py``.
In offline mode (default), tests replay recorded cassettes.  With
``FORCE_MARKET_OPEN=1`` + valid ``DHAN_SANDBOX_CLIENT_ID`` /
``DHAN_SANDBOX_ACCESS_TOKEN`` env vars, tests hit the live Dhan sandbox
and record new cassettes.

Cassettes are stored in ``brokers/tests/integration/cassettes/`` and
are safe to commit (auth headers are masked).

To record cassettes::

    FORCE_MARKET_OPEN=1 \\
    DHAN_SANDBOX_CLIENT_ID=... \\
    DHAN_SANDBOX_ACCESS_TOKEN=... \\
    pytest -m live brokers/tests/integration/test_dhan_live_market_data.py

To replay offline (default)::

    pytest brokers/tests/integration/test_dhan_live_market_data.py
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from brokers.dhan.dhan_provider import DhanProvider
from brokers.domain.enums import Exchange
from brokers.domain.instrument import Instrument
from brokers.domain.values import MarketDepth, Quote


# ── Helpers ────────────────────────────────────────────────────────────────


def _make_provider() -> DhanProvider:
    """Create a DhanProvider with dummy credentials.

    When VCR.py cassettes are present, the real HTTP calls are intercepted
    and replayed.  When cassettes are missing in offline mode, tests skip.
    """
    import os

    return DhanProvider(
        client_id=os.environ.get("DHAN_SANDBOX_CLIENT_ID", "dummy_client"),
        access_token=os.environ.get("DHAN_SANDBOX_ACCESS_TOKEN", "dummy_token"),
        instruments={"RELIANCE:NSE": "3456"},
    )


def _reliance(provider: DhanProvider) -> Instrument:
    """Create a RELIANCE instrument bound to the provider."""
    return Instrument(
        symbol="RELIANCE",
        exchange=Exchange.NSE,
        provider=provider,
        security_id="3456",
    )


# ── Market data tests ──────────────────────────────────────────────────────


@pytest.mark.live
class TestDhanLiveMarketData:
    """Market data endpoints — cassette-replayed against Dhan sandbox."""

    @pytest.mark.asyncio
    async def test_get_quote_reliance(self) -> None:
        """Fetch a real quote for RELIANCE via cassette replay."""
        provider = _make_provider()
        inst = _reliance(provider)
        quote = await provider.get_quote(inst)

        assert isinstance(quote, Quote)
        assert quote.symbol == "RELIANCE"
        assert quote.ltp > 0

    @pytest.mark.asyncio
    async def test_get_ltp_reliance(self) -> None:
        """Fetch LTP for RELIANCE via cassette replay."""
        provider = _make_provider()
        inst = _reliance(provider)
        ltp = await provider.get_ltp(inst)

        assert isinstance(ltp, Decimal)
        assert ltp > 0

    @pytest.mark.asyncio
    async def test_get_depth_reliance(self) -> None:
        """Fetch market depth for RELIANCE via cassette replay."""
        provider = _make_provider()
        inst = _reliance(provider)
        depth = await provider.get_depth(inst)

        assert isinstance(depth, MarketDepth)
        assert depth.symbol == "RELIANCE"


@pytest.mark.live
class TestDhanLivePortfolio:
    """Portfolio endpoints — cassette-replayed against Dhan sandbox."""

    @pytest.mark.asyncio
    async def test_get_positions(self) -> None:
        """Fetch positions via cassette replay."""
        provider = _make_provider()
        positions = await provider.get_positions()

        assert isinstance(positions, list)

    @pytest.mark.asyncio
    async def test_get_balance(self) -> None:
        """Fetch fund balance via cassette replay."""
        provider = _make_provider()
        balance = await provider.get_balance()

        assert balance.available_balance >= 0

    @pytest.mark.asyncio
    async def test_get_holdings(self) -> None:
        """Fetch holdings via cassette replay."""
        provider = _make_provider()
        holdings = await provider.get_holdings()

        assert isinstance(holdings, list)

    @pytest.mark.asyncio
    async def test_get_orders(self) -> None:
        """Fetch order book via cassette replay."""
        provider = _make_provider()
        orders = await provider.get_orders()

        assert isinstance(orders, list)

    @pytest.mark.asyncio
    async def test_get_trades(self) -> None:
        """Fetch trade book via cassette replay."""
        provider = _make_provider()
        trades = await provider.get_trades()

        assert isinstance(trades, list)


@pytest.mark.live
class TestDhanLiveIdentity:
    """Identity and lifecycle — no network calls needed."""

    def test_broker_id(self) -> None:
        provider = _make_provider()
        assert provider.broker_id == "dhan"

    def test_capabilities(self) -> None:
        provider = _make_provider()
        caps = provider.capabilities
        assert caps.broker_id == "dhan"
        assert caps.supports("MARKET_DATA")

    @pytest.mark.asyncio
    async def test_connect_disconnect(self) -> None:
        provider = _make_provider()
        await provider.connect()
        assert provider.is_connected
        # Check stream health when connected but no feeds
        health = provider.stream_health
        assert health.transport.value == "CLOSED"  # No feeds created yet
        await provider.disconnect()
        assert not provider.is_connected

    @pytest.mark.asyncio
    async def test_stream_health_no_feeds(self) -> None:
        """Stream health reports CLOSED when no feeds exist."""
        provider = _make_provider()
        health = provider.stream_health
        assert health.transport.value == "CLOSED"
        assert health.subscription.value == "NONE"
        assert health.detail == "No feeds created"


__all__ = [
    "TestDhanLiveMarketData",
    "TestDhanLivePortfolio",
    "TestDhanLiveIdentity",
]
