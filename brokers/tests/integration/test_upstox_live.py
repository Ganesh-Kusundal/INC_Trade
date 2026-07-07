"""Integration tests for Upstox provider — VCR.py cassette replay.

Mirrors ``brokers/tests/integration/test_dhan_live_market_data.py``.  Uses the
VCR.py cassette framework defined in ``brokers/tests/conftest.py``.  In offline
mode (default) tests replay recorded cassettes; with ``FORCE_MARKET_OPEN=1`` +
valid ``UPSTOX_ACCESS_TOKEN`` env vars, tests hit the live Upstox API and
record new cassettes.

Cassettes live in ``brokers/tests/integration/cassettes/`` and are safe to
commit (auth headers are masked).

To record cassettes::

    FORCE_MARKET_OPEN=1 \\
    UPSTOX_ACCESS_TOKEN=... \\
    pytest -m live brokers/tests/integration/test_upstox_live.py

To replay offline (default)::

    pytest brokers/tests/integration/test_upstox_live.py

The whole module is marked ``@pytest.mark.live`` so it is skipped by default
and never requires credentials to run the suite.  The force-live path also
skips cleanly when credentials are absent.
"""

from __future__ import annotations

import os

import pytest

from brokers.domain.enums import Exchange
from brokers.domain.instrument import Instrument
from brokers.domain.values import MarketDepth, Quote
from brokers.upstox.upstox_provider import UpstoxProvider


# Upstox instrument key format is "EXCHANGE|SECURITY_ID".
_INSTRUMENT_KEY = "NSE_EQ|INE002A01018"


def _has_credentials() -> bool:
    return bool(os.environ.get("UPSTOX_ACCESS_TOKEN"))


def _make_provider() -> UpstoxProvider:
    """Create an UpstoxProvider with dummy or real credentials.

    When VCR.py cassettes are present, the real HTTP calls are intercepted and
    replayed.  When cassettes are missing in offline mode, the conftest skips.
    """
    return UpstoxProvider(
        access_token=os.environ.get("UPSTOX_ACCESS_TOKEN", "dummy_token"),
        instruments={"RELIANCE:NSE": _INSTRUMENT_KEY},
    )


def _reliance(provider: UpstoxProvider) -> Instrument:
    """Create a RELIANCE instrument bound to the provider."""
    return Instrument(
        symbol="RELIANCE",
        exchange=Exchange.NSE,
        provider=provider,
        security_id=_INSTRUMENT_KEY,
    )


@pytest.mark.live
class TestUpstoxLiveMarketData:
    """Market data endpoints — cassette-replayed against Upstox."""

    @pytest.mark.asyncio
    async def test_get_quote_reliance(self) -> None:
        provider = _make_provider()
        inst = _reliance(provider)
        quote = await provider.get_quote(inst)

        assert isinstance(quote, Quote)
        assert quote.symbol == "RELIANCE"
        assert quote.ltp > 0

    @pytest.mark.asyncio
    async def test_get_ltp_reliance(self) -> None:
        from decimal import Decimal

        provider = _make_provider()
        inst = _reliance(provider)
        ltp = await provider.get_ltp(inst)

        assert isinstance(ltp, Decimal)
        assert ltp > 0

    @pytest.mark.asyncio
    async def test_get_depth_reliance(self) -> None:
        provider = _make_provider()
        inst = _reliance(provider)
        depth = await provider.get_depth(inst)

        assert isinstance(depth, MarketDepth)
        assert depth.symbol == "RELIANCE"


@pytest.mark.live
class TestUpstoxLivePortfolio:
    """Portfolio endpoints — cassette-replayed against Upstox."""

    @pytest.mark.asyncio
    async def test_get_positions(self) -> None:
        provider = _make_provider()
        positions = await provider.get_positions()
        assert isinstance(positions, list)

    @pytest.mark.asyncio
    async def test_get_balance(self) -> None:
        from brokers.domain.values import Balance

        provider = _make_provider()
        balance = await provider.get_balance()
        assert isinstance(balance, Balance)
        assert balance.available_balance >= 0

    @pytest.mark.asyncio
    async def test_get_orders(self) -> None:
        provider = _make_provider()
        orders = await provider.get_orders()
        assert isinstance(orders, list)


@pytest.mark.live
class TestUpstoxLiveIdentity:
    """Identity and lifecycle — no network calls needed."""

    def test_broker_id(self) -> None:
        provider = _make_provider()
        assert provider.broker_id == "upstox"

    @pytest.mark.asyncio
    async def test_connect_disconnect(self) -> None:
        provider = _make_provider()
        await provider.connect()
        assert provider.is_connected
        await provider.disconnect()
        assert not provider.is_connected


# Force-live path (FORCE_MARKET_OPEN=1) must not attempt a real call without
# credentials; the conftest handles cassette replay, this only guards the
# live network attempt.
pytestmark = pytest.mark.skipif(
    os.environ.get("FORCE_MARKET_OPEN") == "1" and not _has_credentials(),
    reason="Upstox live test requires UPSTOX_ACCESS_TOKEN when FORCE_MARKET_OPEN=1",
)


__all__ = [
    "TestUpstoxLiveMarketData",
    "TestUpstoxLivePortfolio",
    "TestUpstoxLiveIdentity",
]
