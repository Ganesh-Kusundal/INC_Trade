"""Provider protocol contract test suite.

Verifies that each Provider implementation conforms to the Provider
protocol. Tests against Paper (no credentials), Dhan (mocked HTTP),
and Upstox (mocked HTTP).

This suite tests structural conformance — every Provider must:
  - Return typed domain objects from market data methods
  - Return proper portfolio collections
  - Support lifecycle (connect/disconnect)
  - Support streaming subscriptions
  - Export broker_id, capabilities, extensions, is_connected

The 644 existing unit/integration tests already cover provider methods
in depth with realistic mock data.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from brokers.domain.capabilities import ProviderCapabilities
from brokers.domain.enums import Exchange
from brokers.domain.instrument import Instrument
from brokers.domain.values import (
    Balance,
    Holding,
    MarketDepth,
    OrderResponse,
    Position,
    Quote,
    Subscription,
    Trade,
)
from brokers.provider.protocol import Provider


# ── Base contract suite ─────────────────────────────────────────────────────


class ProviderContractSuite:
    """Every Provider must pass these contract tests.

    Not collected by pytest (class name doesn't start with 'Test').
    Concrete subclasses must implement ``make_provider()`` and
    ``_instrument()``.
    """

    def make_provider(self) -> Provider:
        raise NotImplementedError

    def _instrument(self, provider: Provider | None = None) -> Instrument:
        raise NotImplementedError

    # ── Identity ────────────────────────────────────────────────────────

    def test_broker_id_is_string(self) -> None:
        provider = self.make_provider()
        assert isinstance(provider.broker_id, str)
        assert len(provider.broker_id) > 0

    def test_capabilities_is_provider_capabilities(self) -> None:
        provider = self.make_provider()
        assert isinstance(provider.capabilities, ProviderCapabilities)

    def test_capabilities_supports_core(self) -> None:
        provider = self.make_provider()
        caps = provider.capabilities
        assert caps.supports("MARKET_DATA") is True
        assert caps.supports("PORTFOLIO") is True

    def test_extensions_accessible(self) -> None:
        provider = self.make_provider()
        assert provider.extensions is not None

    def test_is_connected_is_bool(self) -> None:
        provider = self.make_provider()
        assert isinstance(provider.is_connected, bool)

    # ── Lifecycle ────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_connect_disconnect(self) -> None:
        provider = self.make_provider()
        await provider.connect()
        assert provider.is_connected is True
        await provider.disconnect()
        assert provider.is_connected is False

    @pytest.mark.asyncio
    async def test_connect_idempotent(self) -> None:
        provider = self.make_provider()
        await provider.connect()
        await provider.connect()
        assert provider.is_connected is True

    # ── Market data — structural return types ─────────────────────────────

    @pytest.mark.asyncio
    async def test_get_quote_returns_quote(self) -> None:
        provider = self.make_provider()
        inst = self._instrument(provider)
        quote = await provider.get_quote(inst)
        assert isinstance(quote, Quote)
        assert quote.symbol == inst.symbol
        assert quote.ltp > 0

    @pytest.mark.asyncio
    async def test_get_ltp_returns_decimal(self) -> None:
        from decimal import Decimal

        provider = self.make_provider()
        ltp = await provider.get_ltp(self._instrument(provider))
        assert isinstance(ltp, Decimal)

    @pytest.mark.asyncio
    async def test_get_depth_returns_market_depth(self) -> None:
        provider = self.make_provider()
        depth = await provider.get_depth(self._instrument(provider))
        assert isinstance(depth, MarketDepth)
        assert depth.symbol

    # ── Portfolio — structural return types ───────────────────────────────

    @pytest.mark.asyncio
    async def test_get_positions_returns_list(self) -> None:
        provider = self.make_provider()
        positions = await provider.get_positions()
        assert isinstance(positions, list)
        for p in positions:
            assert isinstance(p, Position)

    @pytest.mark.asyncio
    async def test_get_balance_returns_balance(self) -> None:
        provider = self.make_provider()
        balance = await provider.get_balance()
        assert isinstance(balance, Balance)

    @pytest.mark.asyncio
    async def test_get_orders_returns_list(self) -> None:
        provider = self.make_provider()
        orders = await provider.get_orders()
        assert isinstance(orders, list)

    @pytest.mark.asyncio
    async def test_get_trades_returns_list(self) -> None:
        provider = self.make_provider()
        trades = await provider.get_trades()
        assert isinstance(trades, list)
        for t in trades:
            assert isinstance(t, Trade)

    @pytest.mark.asyncio
    async def test_get_holdings_returns_list(self) -> None:
        provider = self.make_provider()
        holdings = await provider.get_holdings()
        assert isinstance(holdings, list)
        for h in holdings:
            assert isinstance(h, Holding)

    # ── Execution — structural return types ───────────────────────────────

    @pytest.mark.asyncio
    async def test_cancel_order_returns_order_response(self) -> None:
        provider = self.make_provider()
        response = await provider.cancel_order("nonexistent")
        assert isinstance(response, OrderResponse)

    # ── Streaming — structural return types ───────────────────────────────

    @pytest.mark.asyncio
    async def test_subscribe_quotes_returns_subscription(self) -> None:
        provider = self.make_provider()
        sub = await provider.subscribe_quotes([self._instrument(provider)])
        assert isinstance(sub, Subscription)

    @pytest.mark.asyncio
    async def test_subscribe_depth_returns_subscription(self) -> None:
        provider = self.make_provider()
        sub = await provider.subscribe_depth([self._instrument(provider)])
        assert isinstance(sub, Subscription)

    @pytest.mark.asyncio
    async def test_subscribe_orders_returns_subscription(self) -> None:
        provider = self.make_provider()
        sub = await provider.subscribe_orders()
        assert isinstance(sub, Subscription)

    @pytest.mark.asyncio
    async def test_unsubscribe_cancels(self) -> None:
        provider = self.make_provider()
        sub = await provider.subscribe_orders()
        await provider.unsubscribe(sub)
        # Cancellation should succeed without error


# ── Paper provider contract tests ───────────────────────────────────────────


class TestPaperProviderContract(ProviderContractSuite):
    """Paper provider contract — no mocking needed, fully self-contained."""

    def make_provider(self) -> Provider:
        from brokers.paper.paper_provider import PaperProvider

        p = PaperProvider()
        # Ensure RELIANCE is seeded (PaperProvider seeds defaults in __init__)
        return p  # type: ignore[return-value]

    def _instrument(self, provider: Provider | None = None) -> Instrument:
        if provider is None:
            provider = self.make_provider()
        return Instrument(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            provider=provider,  # type: ignore[arg-type]
        )


# ── Dhan provider contract tests ────────────────────────────────────────────


class TestDhanProviderContract(ProviderContractSuite):
    """Dhan provider contract — mocked HTTP client + streaming feeds."""

    def make_provider(self) -> Provider:
        from brokers.dhan.dhan_provider import DhanProvider

        mock = MagicMock()
        mock.client_id = "test"
        mock.get_quote.return_value = {
            "data": {
                "NSE_EQ": {
                    "3456": {
                        "last_price": "2550.50",
                        "ohlc": {"open": "2540", "high": "2560", "low": "2530", "close": "2545"},
                        "depth": {"buy": [], "sell": []},
                    }
                }
            }
        }
        mock.get_ltp.return_value = {
            "data": {"NSE_EQ": {"3456": {"last_price": "2550.50"}}}
        }
        mock.get_funds.return_value = {
            "data": {"availabelBalance": "100000"}
        }
        mock.get_positions.return_value = {"data": []}
        mock.get_orderbook.return_value = {"data": []}
        mock.get_trades.return_value = {"data": []}
        mock.get_holdings.return_value = {"data": []}
        mock.cancel_order.return_value = {"status": "success"}

        p = DhanProvider(
            client_id="test",
            access_token="tok",
            instruments={"RELIANCE:NSE": "3456"},
        )
        p._client = mock

        # Pre-set mock streaming feeds so _ensure_* methods return immediately
        p._market_feed = MagicMock()
        p._market_feed.is_running = True
        p._market_feed._orchestrator = MagicMock()
        p._market_feed.subscribe = AsyncMock()
        p._market_feed.unsubscribe = AsyncMock()
        p._market_feed.stop = AsyncMock()

        p._depth_feed = MagicMock()
        p._depth_feed.is_running = True
        p._depth_feed.subscribe = AsyncMock()
        p._depth_feed.unsubscribe = AsyncMock()
        p._depth_feed.stop = AsyncMock()

        p._order_feed = MagicMock()
        p._order_feed.is_running = True
        p._order_feed._orchestrator = MagicMock()
        p._order_feed.stop = AsyncMock()

        return p  # type: ignore[return-value]

    def _instrument(self, provider: Provider | None = None) -> Instrument:
        if provider is None:
            provider = self.make_provider()
        return Instrument(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            provider=provider,  # type: ignore[arg-type]
            security_id="3456",
        )


# ── Upstox provider contract tests ──────────────────────────────────────────


class TestUpstoxProviderContract(ProviderContractSuite):
    """Upstox provider contract — mocked HTTP client + streaming feeds."""

    def make_provider(self) -> Provider:
        from brokers.upstox.upstox_provider import UpstoxProvider

        ik = "NSE_EQ|INE002A01018"
        mock = MagicMock()
        mock.get_quote.return_value = {
            "data": {
                ik: {
                    "last_price": "2550.50",
                    "ohlc": {"open": "2540", "high": "2560", "low": "2530", "close": "2545"},
                    "depth": {"bids": [], "asks": []},
                }
            }
        }
        mock.get_ltp.return_value = {
            "data": {ik: {"last_price": "2550.50"}}
        }
        mock.get_funds.return_value = {
            "data": {"equity": {"available_margin": "100000"}}
        }
        mock.get_positions.return_value = {"data": []}
        mock.get_orderbook.return_value = {"data": []}
        mock.get_trades.return_value = {"data": []}
        mock.get_holdings.return_value = {"data": []}
        mock.cancel_order.return_value = {"status": "success"}

        p = UpstoxProvider(
            access_token="tok",
            instruments={"RELIANCE:NSE": ik},
        )
        p._client = mock

        # Pre-set mock streaming feeds so _ensure_* methods return immediately
        p._market_feed = MagicMock()
        p._market_feed.is_running = True
        p._market_feed._orchestrator = MagicMock()
        p._market_feed.subscribe = AsyncMock()
        p._market_feed.unsubscribe = AsyncMock()
        p._market_feed.stop = AsyncMock()

        p._portfolio_stream = MagicMock()
        p._portfolio_stream.is_running = True
        p._portfolio_stream._orchestrator = MagicMock()
        p._portfolio_stream.stop = AsyncMock()

        return p  # type: ignore[return-value]

    def _instrument(self, provider: Provider | None = None) -> Instrument:
        if provider is None:
            provider = self.make_provider()
        return Instrument(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            provider=provider,  # type: ignore[arg-type]
            security_id="NSE_EQ|INE002A01018",
        )


__all__ = [
    "ProviderContractSuite",
    "TestPaperProviderContract",
    "TestDhanProviderContract",
    "TestUpstoxProviderContract",
]
