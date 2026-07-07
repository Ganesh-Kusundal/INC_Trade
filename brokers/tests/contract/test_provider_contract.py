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

from unittest.mock import AsyncMock, MagicMock, create_autospec

import pytest

from brokers.domain.account import Account
from brokers.domain.capabilities import ProviderCapabilities
from brokers.domain.enums import Exchange, OrderType, Side
from brokers.domain.historical import HistoricalSeries
from brokers.domain.instrument import Instrument
from brokers.domain.option_chain import FutureChain, OptionChain
from brokers.domain.requests import ModifyOrderRequest, OrderRequest
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

    # ── Structural: protocol conformance ─────────────────────────────

    def test_provider_satisfies_provider_protocol(self) -> None:
        """Each concrete provider must be a runtime instance of Provider.

        ``Provider`` is ``runtime_checkable``; this catches silent
        false-green if a real method were renamed and dropped.
        """
        provider = self.make_provider()
        assert isinstance(provider, Provider)

    # ── Execution — full request/response lifecycle ──────────────────

    @pytest.mark.asyncio
    async def test_place_order_returns_order_response(self) -> None:
        provider = self.make_provider()
        request = OrderRequest(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            side=Side.BUY,
            quantity=1,
            order_type=OrderType.MARKET,
        )
        response = await provider.place_order(request)
        assert isinstance(response, OrderResponse)

    @pytest.mark.asyncio
    async def test_modify_order_returns_order_response(self) -> None:
        provider = self.make_provider()
        request = ModifyOrderRequest(order_id="ORD_TEST", quantity=2)
        response = await provider.modify_order(request)
        assert isinstance(response, OrderResponse)

    # ── Market data — derived series ─────────────────────────────────

    @pytest.mark.asyncio
    async def test_get_history_returns_historical_series(self) -> None:
        provider = self.make_provider()
        series = await provider.get_history(self._instrument(provider), bars=3)
        assert isinstance(series, HistoricalSeries)
        assert series.symbol

    @pytest.mark.asyncio
    async def test_get_option_chain_returns_option_chain(self) -> None:
        provider = self.make_provider()
        chain = await provider.get_option_chain(self._instrument(provider))
        assert isinstance(chain, OptionChain)
        assert chain.underlying is not None

    @pytest.mark.asyncio
    async def test_get_future_chain_returns_future_chain(self) -> None:
        provider = self.make_provider()
        chain = await provider.get_future_chain(self._instrument(provider))
        assert isinstance(chain, FutureChain)
        assert chain.underlying is not None

    # ── Instrument discovery ─────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_resolve_instrument_returns_instrument(self) -> None:
        provider = self.make_provider()
        inst = await provider.resolve_instrument("RELIANCE", "NSE")
        assert isinstance(inst, Instrument)
        assert inst.symbol == "RELIANCE"

    @pytest.mark.asyncio
    async def test_get_instruments_returns_list(self) -> None:
        provider = self.make_provider()
        instruments = await provider.get_instruments()
        assert isinstance(instruments, list)
        assert instruments  # at least the seeded RELIANCE
        for i in instruments:
            assert isinstance(i, Instrument)

    @pytest.mark.asyncio
    async def test_search_instruments_returns_list(self) -> None:
        provider = self.make_provider()
        found = await provider.search_instruments("REL")
        assert isinstance(found, list)
        for i in found:
            assert isinstance(i, Instrument)

    # ── Identity — default account ──────────────────────────────────

    def test_default_account_is_account(self) -> None:
        provider = self.make_provider()
        account = provider.default_account
        assert isinstance(account, Account)


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
        from brokers.dhan.client import DhanHttpClient
        from brokers.dhan.dhan_provider import DhanProvider

        # autospec: a renamed real client method would break this contract
        # test (catch silent false-green) instead of being swallowed.
        mock = create_autospec(DhanHttpClient, instance=True)
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
        # New protocol methods exercised by the contract suite.
        mock.post.return_value = {
            "data": {"ohlc": {"candles": [
                [1704069900, "2500.00", "2510.00", "2490.00", "2505.00", 1000]
            ]}}
        }
        mock.get_option_chain.return_value = {"data": []}
        mock.place_order.return_value = {
            "status": "success", "data": {"orderId": "ORD1"}
        }
        mock.modify_order.return_value = {
            "status": "success", "data": {"orderId": "ORD1"}
        }

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
        p._order_feed.add_subscriber = MagicMock()
        p._order_feed.remove_subscriber = AsyncMock()

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
        from brokers.upstox.client import UpstoxHttpClient
        from brokers.upstox.upstox_provider import UpstoxProvider

        ik = "NSE_EQ|INE002A01018"
        # autospec: a renamed real client method would break this contract
        # test (catch silent false-green) instead of being swallowed.
        mock = create_autospec(UpstoxHttpClient, instance=True)
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
        # New protocol methods exercised by the contract suite.
        mock.get_historical_candles.return_value = {
            "data": {"candles": [
                ["2024-01-01T09:15:00", 2500.0, 2510.0, 2490.0, 2505.0, 1000]
            ]}
        }
        mock.get_option_chain.return_value = {"data": []}
        mock.place_order.return_value = {"data": {"order_id": "ORD1"}}
        mock.modify_order.return_value = {"status": "success"}

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

    @pytest.mark.asyncio
    async def test_get_future_chain_returns_future_chain(self) -> None:
        """Upstox does not implement futures chains.

        The contract permits ``NotSupportedError`` for unsupported
        operations — a provider must fail loudly, not silently.
        """
        from brokers.domain.exceptions import NotSupportedError

        provider = self.make_provider()
        with pytest.raises(NotSupportedError):
            await provider.get_future_chain(self._instrument(provider))


# ── Composite provider contract tests ────────────────────────────────────────


class TestCompositeProviderContract(ProviderContractSuite):
    """Composite provider contract — built from two in-memory Paper providers.

    Exercises the *same* base suite against a CompositeProvider to verify
    routing/failover forwards every protocol method to a healthy member.
    Both members are real :class:`PaperProvider` instances (in-memory, no
    credentials), so the composite is exercised against authentic behavior.
    """

    def make_provider(self) -> Provider:
        from brokers.paper.paper_provider import PaperProvider
        from brokers.provider.composite import CompositeProvider

        primary = PaperProvider()
        secondary = PaperProvider()
        composite = CompositeProvider([primary, secondary])
        return composite  # type: ignore[return-value]

    def _instrument(self, provider: Provider | None = None) -> Instrument:
        if provider is None:
            provider = self.make_provider()
        return Instrument(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            provider=provider,  # type: ignore[arg-type]
        )


__all__ = [
    "ProviderContractSuite",
    "TestPaperProviderContract",
    "TestDhanProviderContract",
    "TestUpstoxProviderContract",
    "TestCompositeProviderContract",
]
