"""Tests for MarketDataConfig and its integration with MarketDataContext."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, is_dataclass
from typing import Any

from brokers.market.config import MarketDataConfig
from brokers.market import MarketDataConfig as Exported
from brokers.market.context import MarketDataContext
from brokers.market.instrument import Instrument
from brokers.market.instrument_registry import InstrumentRegistry

# ── Fakes (duplicated locally to keep this test file self-contained) ─────


class _FakeMarketData:
    def ltp(self, symbol: str, exchange: str) -> Any:  # pragma: no cover - not used here
        return None

    def quote(self, symbol: str, exchange: str) -> Any:  # pragma: no cover - not used here
        return None

    def depth(self, symbol: str, exchange: str) -> Any:  # pragma: no cover - not used here
        return None

    def ltp_batch(self, items: list[tuple[str, str]]) -> list[Any]:  # pragma: no cover
        return []

    def quote_batch(self, items: list[tuple[str, str]]) -> list[Any]:  # pragma: no cover
        return []


class _FakeHistorical:
    def get_historical_candles(  # pragma: no cover - not used here
        self,
        symbol: str,
        exchange: str,
        interval: str,
        from_date: Any,
        to_date: Any,
    ) -> list[Any]:
        return []


class _FakeOptions:
    def get_expiries(self, symbol: str, exchange: str) -> list[Any]:  # pragma: no cover
        return []

    def get_option_chain(self, symbol: str, exchange: str, expiry: Any) -> Any:  # pragma: no cover
        return None


class _FakeStreaming:
    def __init__(self) -> None:
        self._connected = False

    def subscribe(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
        return None

    def unsubscribe(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
        return None

    async def connect(self) -> None:  # pragma: no cover
        self._connected = True

    async def disconnect(self) -> None:  # pragma: no cover
        self._connected = False

    def is_connected(self) -> bool:  # pragma: no cover
        return self._connected

    async def subscribe_quotes(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover
        return None

    async def unsubscribe_quotes(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover
        return None


def _make_registry() -> InstrumentRegistry:
    reg = InstrumentRegistry()
    inst = Instrument(
        symbol="RELIANCE",
        exchange="NSE",
        segment="NSE_EQ",
        name="Reliance Industries",
        lot_size=1,
    )
    reg.get_or_create("NSE:RELIANCE", lambda: inst)
    return reg


# ── MarketDataConfig dataclass tests ─────────────────────────────────────


class TestMarketDataConfig:
    """Unit tests for the MarketDataConfig dataclass itself."""

    def test_is_dataclass(self) -> None:
        assert is_dataclass(MarketDataConfig)

    def test_default_values(self) -> None:
        config = MarketDataConfig()
        assert config.historical is None
        assert config.historical_router is None
        assert config.options is None
        assert config.streaming is None
        assert config.instrument_port is None
        assert config.subscription_manager is None
        assert config.streaming_router is None
        assert config.event_bus is None
        assert config.broker_id == ""
        assert config.market_router is None

    def test_field_assignment(self) -> None:
        sentinel: Any = object()
        config = MarketDataConfig(
            historical=sentinel,
            historical_router="h_router",
            options="opts",
            streaming="stream",
            instrument_port="inst",
            subscription_manager="sub_man",
            streaming_router="s_router",
            event_bus="bus",
            broker_id="DHAN",
            market_router="m_router",
        )
        assert config.historical is sentinel
        assert config.historical_router == "h_router"
        assert config.options == "opts"
        assert config.streaming == "stream"
        assert config.instrument_port == "inst"
        assert config.subscription_manager == "sub_man"
        assert config.streaming_router == "s_router"
        assert config.event_bus == "bus"
        assert config.broker_id == "DHAN"
        assert config.market_router == "m_router"

    def test_is_frozen(self) -> None:
        config = MarketDataConfig(broker_id="X")
        try:
            config.broker_id = "Y"  # type: ignore[misc]
        except FrozenInstanceError:
            return
        raise AssertionError("Expected FrozenInstanceError on attribute assignment")

    def test_is_hashable(self) -> None:
        config = MarketDataConfig(broker_id="DHAN")
        # Should be hashable (frozen dataclasses are hashable by default).
        assert hash(config) == hash(MarketDataConfig(broker_id="DHAN"))


# ── MarketDataContext + MarketDataConfig integration tests ──────────────


class TestMarketDataContextWithConfig:
    """Integration tests for MarketDataConfig + MarketDataContext."""

    def test_config_wires_all_fields(self) -> None:
        registry = _make_registry()
        market_data = _FakeMarketData()
        historical = _FakeHistorical()
        options = _FakeOptions()
        streaming = _FakeStreaming()
        event_bus: Any = object()
        market_router: Any = object()

        config = MarketDataConfig(
            historical=historical,
            options=options,
            streaming=streaming,
            event_bus=event_bus,
            broker_id="DHAN",
            market_router=market_router,
        )

        ctx = MarketDataContext(registry=registry, market_data=market_data, config=config)

        # Required deps are wired.
        assert ctx._registry is registry
        assert ctx._market_data is market_data

        # Config-driven fields are wired.
        assert ctx._historical is historical
        assert ctx._options is options
        assert ctx._streaming is streaming
        assert ctx._event_bus is event_bus
        assert ctx._broker_id == "DHAN"
        assert ctx._market_router is market_router

        # Unset config fields stay None (no kwargs override).
        assert ctx._historical_router is None
        assert ctx._instrument_port is None
        assert ctx._subscription_manager is None
        assert ctx._streaming_router is None

    def test_config_can_be_empty(self) -> None:
        """An empty MarketDataConfig is equivalent to passing no kwargs."""
        registry = _make_registry()
        market_data = _FakeMarketData()
        ctx = MarketDataContext(
            registry=registry, market_data=market_data, config=MarketDataConfig()
        )
        assert ctx._registry is registry
        assert ctx._market_data is market_data
        assert ctx._historical is None
        assert ctx._options is None
        assert ctx._streaming is None
        assert ctx._broker_id == ""
        assert ctx._market_router is None

    def test_backward_compat_kwargs_only(self) -> None:
        """All-keyword call site must still work exactly as before."""
        registry = _make_registry()
        market_data = _FakeMarketData()
        historical = _FakeHistorical()
        options = _FakeOptions()
        streaming = _FakeStreaming()

        ctx = MarketDataContext(
            registry=registry,
            market_data=market_data,
            historical=historical,
            options=options,
            streaming=streaming,
        )

        assert ctx._registry is registry
        assert ctx._market_data is market_data
        assert ctx._historical is historical
        assert ctx._options is options
        assert ctx._streaming is streaming
        assert ctx._broker_id == ""
        assert ctx._market_router is None

    def test_config_wins_over_kwargs(self) -> None:
        """When both config and individual kwargs are passed, config wins."""
        registry = _make_registry()
        market_data = _FakeMarketData()
        kw_historical = _FakeHistorical()
        kw_options = _FakeOptions()
        kw_streaming = _FakeStreaming()

        cfg_historical = _FakeHistorical()
        cfg_options = _FakeOptions()
        cfg_streaming = _FakeStreaming()
        config = MarketDataConfig(
            historical=cfg_historical,
            options=cfg_options,
            streaming=cfg_streaming,
            broker_id="FROM_CONFIG",
        )

        ctx = MarketDataContext(
            registry=registry,
            market_data=market_data,
            config=config,
            historical=kw_historical,
            options=kw_options,
            streaming=kw_streaming,
            broker_id="FROM_KWARG",
        )

        # Config values take precedence.
        assert ctx._historical is cfg_historical
        assert ctx._options is cfg_options
        assert ctx._streaming is cfg_streaming
        assert ctx._broker_id == "FROM_CONFIG"

        # Confirm the kwargs really were the *other* objects (sanity check).
        assert cfg_historical is not kw_historical
        assert cfg_options is not kw_options
        assert cfg_streaming is not kw_streaming

    def test_legacy_construction_unchanged(self) -> None:
        """Existing positional-arg call sites still work."""
        registry = _make_registry()
        market_data = _FakeMarketData()
        # Positional: (registry, market_data) — no other args.
        ctx = MarketDataContext(registry, market_data)
        assert ctx._registry is registry
        assert ctx._market_data is market_data
        assert ctx._historical is None
        assert ctx._broker_id == ""


# ── Export tests ─────────────────────────────────────────────────────────


class TestMarketDataConfigExport:
    """MarketDataConfig must be exported from brokers.market."""

    def test_exported_from_market_package(self) -> None:
        from brokers.market import MarketDataConfig as Exported

        assert Exported is MarketDataConfig

    def test_in_market_all(self) -> None:
        import brokers.market as market_module

        assert "MarketDataConfig" in market_module.__all__
