"""Unit tests for BrokerSession, brokers.connect(), and _underlying_gateway deprecation."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

if TYPE_CHECKING:
    from inc_trade.adapters.broker_adapter import BrokerAdapter

import pytest
from inc_trade.services.broker_session import BrokerSession

import brokers

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_ports() -> dict:
    """Return a dict of mock port objects."""
    streaming = MagicMock()
    streaming.disconnect = AsyncMock()
    return {
        "orders": MagicMock(name="orders_port"),
        "market": MagicMock(name="market_data_port"),
        "streaming": streaming,
        "auth": MagicMock(name="auth_port"),
        "portfolio": MagicMock(name="portfolio_port"),
        "historical": MagicMock(name="historical_port"),
    }


@pytest.fixture()
def ports() -> dict:
    return _make_ports()


@pytest.fixture()
def session(ports: dict) -> BrokerSession:
    return BrokerSession(broker_id="test_broker", **ports)


# ---------------------------------------------------------------------------
# 1. BrokerSession construction
# ---------------------------------------------------------------------------


class TestBrokerSessionConstruction:
    def test_constructs_with_all_ports(self, ports: dict) -> None:
        sess = BrokerSession(broker_id="dhan", **ports)
        assert isinstance(sess, BrokerSession)

    def test_broker_id_stored(self, session: BrokerSession) -> None:
        assert session.broker_id == "test_broker"

    def test_repr_contains_broker_id(self, session: BrokerSession) -> None:
        assert "test_broker" in repr(session)
        assert repr(session) == "BrokerSession(broker_id='test_broker')"


# ---------------------------------------------------------------------------
# 2. Property accessors
# ---------------------------------------------------------------------------


class TestBrokerSessionProperties:
    def test_orders_property(self, session: BrokerSession, ports: dict) -> None:
        assert session.orders is ports["orders"]

    def test_market_property(self, session: BrokerSession, ports: dict) -> None:
        assert session.market is ports["market"]

    def test_streaming_property(self, session: BrokerSession, ports: dict) -> None:
        assert session.streaming is ports["streaming"]

    def test_auth_property(self, session: BrokerSession, ports: dict) -> None:
        assert session.auth is ports["auth"]

    def test_portfolio_property(self, session: BrokerSession, ports: dict) -> None:
        assert session.portfolio is ports["portfolio"]

    def test_historical_property(self, session: BrokerSession, ports: dict) -> None:
        assert session.historical is ports["historical"]


# ---------------------------------------------------------------------------
# 3. close() behaviour
# ---------------------------------------------------------------------------


class TestBrokerSessionClose:
    def test_close_calls_streaming_disconnect_sync(self) -> None:
        """When disconnect is a plain callable (non-async), it is called."""
        streaming = MagicMock()
        streaming.disconnect = MagicMock(return_value=None)  # sync mock

        ports = _make_ports()
        ports["streaming"] = streaming

        sess = BrokerSession(broker_id="paper", **ports)
        sess.close()

        streaming.disconnect.assert_called_once()

    def test_close_with_async_disconnect_schedules_coroutine(self) -> None:
        """When disconnect returns a coroutine, BrokerSession handles it gracefully."""
        import asyncio

        coroutine_started = []

        async def _fake_disconnect() -> None:
            coroutine_started.append(True)

        streaming = MagicMock()
        streaming.disconnect = _fake_disconnect  # async def, returns a coroutine

        ports = _make_ports()
        ports["streaming"] = streaming

        sess = BrokerSession(broker_id="paper", **ports)

        # Run close() inside an event loop so create_task can work.
        async def _runner() -> None:
            sess.close()
            await asyncio.sleep(0)  # yield to let created task run

        asyncio.run(_runner())
        assert coroutine_started, "async disconnect was never awaited"

    def test_close_handles_missing_disconnect(self) -> None:
        """If streaming port has no disconnect attribute, close() doesn't raise."""
        streaming = MagicMock(spec=[])  # spec with NO attributes

        ports = _make_ports()
        ports["streaming"] = streaming

        sess = BrokerSession(broker_id="paper", **ports)
        sess.close()  # must not raise

    def test_close_handles_none_streaming(self) -> None:
        """If streaming is None (hypothetical), close() doesn't raise."""
        ports = _make_ports()
        sess = BrokerSession(broker_id="paper", **ports)
        sess._streaming = None  # type: ignore[assignment]
        sess.close()  # must not raise


# ---------------------------------------------------------------------------
# 4. brokers.connect() public API
# ---------------------------------------------------------------------------


class TestBrokersConnect:
    def test_connect_is_importable(self) -> None:
        assert callable(brokers.connect)

    def test_connect_paper_returns_broker_session(self) -> None:
        session = brokers.connect("paper")
        assert isinstance(session, BrokerSession)
        assert session.broker_id == "paper"

    def test_connect_paper_wires_all_ports(self) -> None:
        session = brokers.connect("paper")
        assert session.orders is not None
        assert session.market is not None
        assert session.streaming is not None
        assert session.auth is not None
        assert session.portfolio is not None
        assert session.historical is not None

    def test_connect_with_broker_id_enum(self) -> None:
        from inc_trade.domain.enums import BrokerID

        session = brokers.connect(BrokerID.PAPER)
        assert isinstance(session, BrokerSession)

    def test_connect_unknown_broker_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown broker"):
            brokers.connect("nonexistent_broker_xyz")


# ---------------------------------------------------------------------------
# 5. DeprecationWarning on _underlying_gateway
# ---------------------------------------------------------------------------


class TestUnderlyingGatewayDeprecation:
    def test_underlying_gateway_accessible(self) -> None:
        from typing import cast

        from inc_trade.ports.extension_registry import DictExtensionRegistry
        from inc_trade.services.broker_facade import BrokerFacade

        from brokers.adapters.paper.gateway import PaperGateway

        gw = PaperGateway()
        facade = BrokerFacade(cast("BrokerAdapter", gw), extension_registry=DictExtensionRegistry())

        # _underlying_gateway is kept for compatibility
        _ = facade._underlying_gateway  # no warning expected
