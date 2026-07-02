"""Tests for DhanDepth20Feed — 20-level market depth WebSocket."""

from __future__ import annotations

import pytest

from brokers.dhan.depth_20 import DhanDepth20Feed


class TestDhanDepth20Feed:
    """Verify DhanDepth20Feed construction and API surface."""

    def test_depth_20_feed_init(self):
        """Construction with client_id, access_token, and instruments must succeed."""
        instruments = [
            ("NSE_EQ", "2885"),
            ("NSE_EQ", "2886"),
        ]
        feed = DhanDepth20Feed(
            client_id="TEST_CLIENT",
            access_token="TEST_TOKEN",
            instruments=instruments,
        )

        assert feed._client_id == "TEST_CLIENT"
        assert feed._access_token == "TEST_TOKEN"
        assert feed._instruments == instruments
        assert feed.max_instruments == 50
        assert feed.name == "dhan.depth_20"

    def test_depth_20_feed_init_no_instruments(self):
        """Construction without instruments must succeed (subscribe later)."""
        feed = DhanDepth20Feed(
            client_id="CLIENT",
            access_token="TOKEN",
        )
        assert feed._instruments == []
        assert feed._subscriptions == []

    def test_depth_20_max_instruments_50(self):
        """Maximum 50 instruments allowed per connection."""
        assert DhanDepth20Feed.MAX_INSTRUMENTS == 50

    def test_depth_20_subscribe_over_limit_raises(self):
        """Should raise ValueError if >50 instruments."""
        instruments = [("NSE_EQ", str(i)) for i in range(51)]

        with pytest.raises(ValueError, match="Maximum 50 instruments"):
            DhanDepth20Feed(
                client_id="CLIENT",
                access_token="TOKEN",
                instruments=instruments,
            )

    def test_depth_20_subscribe_within_limit(self):
        """Should allow up to 50 instruments."""
        feed = DhanDepth20Feed(
            client_id="CLIENT",
            access_token="TOKEN",
        )

        # Subscribe 50 instruments
        instruments = [("NSE_EQ", str(i)) for i in range(50)]
        feed.subscribe(instruments)

        assert len(feed._subscriptions) == 50

    def test_depth_20_subscribe_over_limit_after_init_raises(self):
        """Should raise ValueError if subscribing over limit after init."""
        feed = DhanDepth20Feed(
            client_id="CLIENT",
            access_token="TOKEN",
            instruments=[("NSE_EQ", "1")],
        )

        # Try to subscribe 50 more (total would be 51)
        instruments = [("NSE_EQ", str(i)) for i in range(2, 52)]

        with pytest.raises(ValueError, match="Maximum 50 instruments"):
            feed.subscribe(instruments)

    def test_depth_20_callback_registration(self):
        """on_depth must accept a callable and store it."""
        feed = DhanDepth20Feed(
            client_id="CLIENT",
            access_token="TOKEN",
        )

        received = []
        feed.on_depth(lambda data: received.append(data))

        assert len(feed._depth_callbacks) == 1
        assert callable(feed._depth_callbacks[0])

    def test_depth_20_multiple_callbacks(self):
        """Multiple callbacks can be registered."""
        feed = DhanDepth20Feed(
            client_id="CLIENT",
            access_token="TOKEN",
        )

        feed.on_depth(lambda d: None)
        feed.on_depth(lambda d: None)
        feed.on_depth(lambda d: None)

        assert len(feed._depth_callbacks) == 3

    def test_depth_20_is_connected_default_false(self):
        """is_connected must be False before connect() is called."""
        feed = DhanDepth20Feed(
            client_id="CLIENT",
            access_token="TOKEN",
        )
        assert feed._is_connected is False

    def test_depth_20_managed_service_protocol(self):
        """DhanDepth20Feed must implement ManagedService protocol."""
        feed = DhanDepth20Feed(
            client_id="CLIENT",
            access_token="TOKEN",
        )

        assert hasattr(feed, "name")
        assert hasattr(feed, "start")
        assert hasattr(feed, "stop")
        assert hasattr(feed, "health")
        assert feed.name == "dhan.depth_20"

    def test_depth_20_health_not_started(self):
        """Health should be STOPPED before start()."""
        from infrastructure.lifecycle.lifecycle import HealthState

        feed = DhanDepth20Feed(
            client_id="CLIENT",
            access_token="TOKEN",
        )

        health = feed.health()
        assert health.state == HealthState.STOPPED
        assert "not started" in health.detail
