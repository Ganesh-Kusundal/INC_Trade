"""Tests for WebSocket auto-wiring in BrokerFactory."""

from __future__ import annotations

from brokers.dhan import BrokerFactory
from infrastructure.event_bus import EventBus
from infrastructure.lifecycle import LifecycleManager
from infrastructure.lifecycle.lifecycle import HealthState


class TestFactoryWebSocketWiring:
    """Verify that BrokerFactory auto-creates and registers WebSocket services."""

    def test_factory_auto_creates_market_feed_with_lifecycle(self, tmp_path):
        """Factory.create() should auto-create DhanMarketFeed when lifecycle provided."""
        env_file = tmp_path / ".env.local"
        env_file.write_text(
            "DHAN_CLIENT_ID=TEST_CLIENT\n"
            "DHAN_ACCESS_TOKEN=test_token\n"
            "DHAN_PIN=1234\n"
            "DHAN_TOTP_SECRET=TESTTOTPSECRET\n"
        )

        lifecycle = LifecycleManager()
        event_bus = EventBus()

        gateway = BrokerFactory().create(
            env_path=env_file,
            load_instruments=False,
            event_bus=event_bus,
            lifecycle=lifecycle,
        )

        assert gateway._conn.market_feed is not None
        assert gateway._conn.market_feed.name == "dhan.market_feed"
        assert "dhan.market_feed" in lifecycle.service_names()

    def test_factory_auto_creates_order_stream_with_lifecycle(self, tmp_path):
        """Factory.create() should auto-create DhanOrderStream when lifecycle provided."""
        env_file = tmp_path / ".env.local"
        env_file.write_text(
            "DHAN_CLIENT_ID=TEST_CLIENT\n"
            "DHAN_ACCESS_TOKEN=test_token\n"
            "DHAN_PIN=1234\n"
            "DHAN_TOTP_SECRET=TESTTOTPSECRET\n"
        )

        lifecycle = LifecycleManager()
        event_bus = EventBus()

        gateway = BrokerFactory().create(
            env_path=env_file,
            load_instruments=False,
            event_bus=event_bus,
            lifecycle=lifecycle,
        )

        assert gateway._conn.order_stream is not None
        assert gateway._conn.order_stream.name == "dhan.order_stream"
        assert "dhan.order_stream" in lifecycle.service_names()

    def test_factory_no_lifecycle_no_auto_wire(self, tmp_path):
        """Without lifecycle, factory should NOT auto-wire (backward compat)."""
        env_file = tmp_path / ".env.local"
        env_file.write_text(
            "DHAN_CLIENT_ID=TEST_CLIENT\n"
            "DHAN_ACCESS_TOKEN=test_token\n"
            "DHAN_PIN=1234\n"
            "DHAN_TOTP_SECRET=TESTTOTPSECRET\n"
        )

        gateway = BrokerFactory().create(
            env_path=env_file,
            load_instruments=False,
        )

        assert gateway._conn.market_feed is None
        assert gateway._conn.order_stream is None

    def test_factory_no_event_bus_no_auto_wire(self, tmp_path):
        """Without event_bus, factory should NOT auto-wire."""
        env_file = tmp_path / ".env.local"
        env_file.write_text(
            "DHAN_CLIENT_ID=TEST_CLIENT\n"
            "DHAN_ACCESS_TOKEN=test_token\n"
            "DHAN_PIN=1234\n"
            "DHAN_TOTP_SECRET=TESTTOTPSECRET\n"
        )

        lifecycle = LifecycleManager()

        gateway = BrokerFactory().create(
            env_path=env_file,
            load_instruments=False,
            lifecycle=lifecycle,
        )

        assert gateway._conn.market_feed is None
        assert gateway._conn.order_stream is None

    def test_factory_websocket_registered_not_started(self, tmp_path):
        """WebSocket services should be registered but not started until lifecycle.start_all()."""
        env_file = tmp_path / ".env.local"
        env_file.write_text(
            "DHAN_CLIENT_ID=TEST_CLIENT\n"
            "DHAN_ACCESS_TOKEN=test_token\n"
            "DHAN_PIN=1234\n"
            "DHAN_TOTP_SECRET=TESTTOTPSECRET\n"
        )

        lifecycle = LifecycleManager()
        event_bus = EventBus()

        gateway = BrokerFactory().create(
            env_path=env_file,
            load_instruments=False,
            event_bus=event_bus,
            lifecycle=lifecycle,
        )

        assert "dhan.market_feed" in lifecycle.service_names()
        assert "dhan.order_stream" in lifecycle.service_names()

        market_feed_health = gateway._conn.market_feed.health()
        order_stream_health = gateway._conn.order_stream.health()

        assert market_feed_health.state == HealthState.STOPPED
        assert order_stream_health.state == HealthState.STOPPED

    def test_websocket_wiring_does_not_replace_factory_order_stream(self, tmp_path):
        """cli websocket_wiring must not create a second order stream."""
        from cli.services.websocket_wiring import start_websocket_services

        env_file = tmp_path / ".env.local"
        env_file.write_text(
            "DHAN_CLIENT_ID=TEST_CLIENT\n"
            "DHAN_ACCESS_TOKEN=test_token\n"
            "DHAN_PIN=1234\n"
            "DHAN_TOTP_SECRET=TESTTOTPSECRET\n"
        )

        lifecycle = LifecycleManager()
        event_bus = EventBus()
        gateway = BrokerFactory().create(
            env_path=env_file,
            load_instruments=False,
            event_bus=event_bus,
            lifecycle=lifecycle,
        )
        factory_stream = gateway._conn.order_stream
        assert factory_stream is not None

        start_websocket_services(gateway, lifecycle)

        assert gateway._conn.order_stream is factory_stream
