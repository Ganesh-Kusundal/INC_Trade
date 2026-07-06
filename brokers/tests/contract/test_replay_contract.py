"""Contract tests — ReplayEngine contract.

Verifies MarketDataPort, HistoricalPort/HistoricalProvider, and
StreamingPort conformance, plus speed control and CSV loading.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from inc_trade.domain.entities import Candle, MarketDepth, Quote


def _make_candle(
    ts: datetime | None = None,
    close: Decimal = Decimal("2500"),
) -> Candle:
    if ts is None:
        ts = datetime(2024, 6, 1, tzinfo=UTC)
    return Candle(
        symbol="RELIANCE",
        timestamp=ts,
        open=close - Decimal("10"),
        high=close + Decimal("20"),
        low=close - Decimal("15"),
        close=close,
        volume=10000,
    )


def _seed_engine(engine: Any) -> None:
    """Populate a ReplayEngine with synthetic candles and quotes."""
    ts = datetime(2024, 6, 1, tzinfo=UTC)
    candle = _make_candle(ts, Decimal("2500"))
    engine._candles_by_key["NSE:RELIANCE"] = [candle]
    engine._quotes_by_key["NSE:RELIANCE"] = [
        Quote(
            symbol="RELIANCE",
            ltp=Decimal("2500"),
            exchange="NSE",
            timestamp=ts,
        ),
    ]


class ReplayContractTests:
    """Mixin-style contract tests for ReplayEngine."""

    # ── MarketDataPort ──────────────────────────────────────────────────

    def test_ltp_returns_decimal(self, engine: Any) -> None:
        price = engine.ltp("RELIANCE", "NSE")
        assert isinstance(price, Decimal)
        assert price > 0

    def test_ltp_raises_key_error_for_unknown_symbol(self, engine: Any) -> None:
        with pytest.raises(KeyError):
            engine.ltp("UNKNOWN", "NSE")

    def test_quote_returns_quote_object(self, engine: Any) -> None:
        q = engine.quote("RELIANCE", "NSE")
        assert isinstance(q, Quote)
        assert q.symbol == "RELIANCE"
        assert q.ltp > 0

    def test_quote_raises_key_error_for_unknown(self, engine: Any) -> None:
        with pytest.raises(KeyError):
            engine.quote("UNKNOWN", "NSE")

    def test_depth_returns_market_depth(self, engine: Any) -> None:
        d = engine.depth("RELIANCE", "NSE")
        assert isinstance(d, MarketDepth)
        assert d.symbol == "RELIANCE"
        assert len(d.bids) > 0
        assert len(d.asks) > 0

    def test_depth_raises_key_error_for_unknown(self, engine: Any) -> None:
        with pytest.raises(KeyError):
            engine.depth("UNKNOWN", "NSE")

    def test_ltp_batch_returns_dict(self, engine: Any) -> None:
        prices = engine.ltp_batch(["RELIANCE"], "NSE")
        assert isinstance(prices, dict)
        assert "RELIANCE" in prices
        assert isinstance(prices["RELIANCE"], Decimal)

    def test_ltp_batch_skips_unknown_symbols(self, engine: Any) -> None:
        prices = engine.ltp_batch(["RELIANCE", "UNKNOWN"], "NSE")
        assert "RELIANCE" in prices
        assert "UNKNOWN" not in prices

    def test_quote_batch_returns_dict(self, engine: Any) -> None:
        quotes = engine.quote_batch(["RELIANCE"], "NSE")
        assert isinstance(quotes, dict)
        assert "RELIANCE" in quotes
        assert isinstance(quotes["RELIANCE"], Quote)

    # ── HistoricalPort / HistoricalProvider ────────────────────────────

    def test_get_historical_candles_returns_list(self, engine: Any) -> None:
        now = datetime.now(UTC)
        candles = engine.get_historical_candles(
            "RELIANCE",
            "NSE",
            now - timedelta(days=365),
            now,
            "1D",
        )
        assert isinstance(candles, list)

    def test_get_historical_candles_returns_candle_type(self, engine: Any) -> None:
        now = datetime.now(UTC)
        candles = engine.get_historical_candles(
            "RELIANCE",
            "NSE",
            now - timedelta(days=365),
            now,
            "1D",
        )
        for c in candles:
            assert isinstance(c, Candle)

    def test_get_historical_candles_empty_for_missing_symbol(self, engine: Any) -> None:
        now = datetime.now(UTC)
        candles = engine.get_historical_candles(
            "UNKNOWN",
            "NSE",
            now - timedelta(days=365),
            now,
            "1D",
        )
        assert candles == []

    def test_provider_id(self, engine: Any) -> None:
        assert engine.provider_id == "replay"

    def test_is_available(self, engine: Any) -> None:
        assert engine.is_available is True

    # ── StreamingPort ──────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_connect_disconnect(self, engine: Any) -> None:
        assert not engine.is_connected
        await engine.connect()
        assert engine.is_connected
        await engine.disconnect()
        assert not engine.is_connected

    @pytest.mark.asyncio
    async def test_subscribe_unsubscribe_quotes(self, engine: Any) -> None:
        received: list[Any] = []

        def cb(data: Any) -> None:
            received.append(data)

        await engine.connect()
        await engine.subscribe_quotes(["RELIANCE"], "NSE", cb)
        assert engine.is_connected
        await engine.unsubscribe_quotes(["RELIANCE"], "NSE")
        await engine.disconnect()

    @pytest.mark.asyncio
    async def test_subscribe_callback_receives_quotes(self, engine: Any) -> None:
        received: list[Any] = []

        def cb(data: Any) -> None:
            received.append(data)

        await engine.connect()
        await engine.subscribe_quotes(["RELIANCE"], "NSE", cb)
        # Give the replay task a moment to dispatch
        await asyncio.sleep(0.05)
        await engine.unsubscribe_quotes(["RELIANCE"], "NSE")
        await engine.disconnect()

        assert len(received) >= 1
        assert isinstance(received[0], Quote)

    # ── Speed control ──────────────────────────────────────────────────

    def test_speed_defaults_to_one(self) -> None:
        from brokers.adapters.replay.engine import ReplayEngine

        eng = ReplayEngine()
        assert eng.speed == 1.0

    def test_speed_setter_clamps_to_zero(self) -> None:
        from brokers.adapters.replay.engine import ReplayEngine

        eng = ReplayEngine(speed=-5)
        assert eng.speed == 0.0

    def test_speed_zero_for_instant_replay(self) -> None:
        from brokers.adapters.replay.engine import ReplayEngine

        eng = ReplayEngine(speed=0)
        assert eng.speed == 0.0
        _seed_engine(eng)

        price = eng.ltp("RELIANCE", "NSE")
        assert price == Decimal("2500")

    # ── CSV loading ────────────────────────────────────────────────────

    def test_csv_dir_nonexistent_does_not_raise(
        self,
    ) -> None:
        from brokers.adapters.replay.engine import ReplayEngine

        eng = ReplayEngine(csv_dir="/nonexistent/path")
        # No exception means success
        assert isinstance(eng.symbols(), list)

    def test_symbols_and_has_symbol(self, engine: Any) -> None:
        assert "NSE:RELIANCE" in engine.symbols()
        assert engine.has_symbol("RELIANCE", "NSE")
        assert not engine.has_symbol("UNKNOWN", "NSE")


@pytest.mark.contract
class TestReplayContractConformance:
    """Base test class — override ``engine`` fixture."""

    @pytest.fixture
    def engine(self) -> Any:
        from brokers.adapters.replay.engine import ReplayEngine

        eng = ReplayEngine(speed=0)
        _seed_engine(eng)
        return eng

    def test_ltp_returns_decimal(self, engine: Any) -> None:
        ReplayContractTests().test_ltp_returns_decimal(engine)

    def test_ltp_raises_key_error_for_unknown_symbol(self, engine: Any) -> None:
        ReplayContractTests().test_ltp_raises_key_error_for_unknown_symbol(engine)

    def test_quote_returns_quote_object(self, engine: Any) -> None:
        ReplayContractTests().test_quote_returns_quote_object(engine)

    def test_quote_raises_key_error_for_unknown(self, engine: Any) -> None:
        ReplayContractTests().test_quote_raises_key_error_for_unknown(engine)

    def test_depth_returns_market_depth(self, engine: Any) -> None:
        ReplayContractTests().test_depth_returns_market_depth(engine)

    def test_depth_raises_key_error_for_unknown(self, engine: Any) -> None:
        ReplayContractTests().test_depth_raises_key_error_for_unknown(engine)

    def test_ltp_batch_returns_dict(self, engine: Any) -> None:
        ReplayContractTests().test_ltp_batch_returns_dict(engine)

    def test_ltp_batch_skips_unknown_symbols(self, engine: Any) -> None:
        ReplayContractTests().test_ltp_batch_skips_unknown_symbols(engine)

    def test_quote_batch_returns_dict(self, engine: Any) -> None:
        ReplayContractTests().test_quote_batch_returns_dict(engine)

    def test_get_historical_candles_returns_list(self, engine: Any) -> None:
        ReplayContractTests().test_get_historical_candles_returns_list(engine)

    def test_get_historical_candles_returns_candle_type(self, engine: Any) -> None:
        ReplayContractTests().test_get_historical_candles_returns_candle_type(engine)

    def test_get_historical_candles_empty_for_missing_symbol(self, engine: Any) -> None:
        ReplayContractTests().test_get_historical_candles_empty_for_missing_symbol(engine)

    def test_provider_id(self, engine: Any) -> None:
        ReplayContractTests().test_provider_id(engine)

    def test_is_available(self, engine: Any) -> None:
        ReplayContractTests().test_is_available(engine)

    @pytest.mark.asyncio
    async def test_connect_disconnect(self, engine: Any) -> None:
        await ReplayContractTests().test_connect_disconnect(engine)

    @pytest.mark.asyncio
    async def test_subscribe_unsubscribe_quotes(self, engine: Any) -> None:
        await ReplayContractTests().test_subscribe_unsubscribe_quotes(engine)

    @pytest.mark.asyncio
    async def test_subscribe_callback_receives_quotes(self, engine: Any) -> None:
        await ReplayContractTests().test_subscribe_callback_receives_quotes(engine)

    def test_speed_defaults_to_one(self) -> None:
        ReplayContractTests().test_speed_defaults_to_one()

    def test_speed_setter_clamps_to_zero(self) -> None:
        ReplayContractTests().test_speed_setter_clamps_to_zero()

    def test_speed_zero_for_instant_replay(self) -> None:
        ReplayContractTests().test_speed_zero_for_instant_replay()

    def test_csv_dir_nonexistent_does_not_raise(self) -> None:
        ReplayContractTests().test_csv_dir_nonexistent_does_not_raise()

    def test_symbols_and_has_symbol(self, engine: Any) -> None:
        ReplayContractTests().test_symbols_and_has_symbol(engine)
