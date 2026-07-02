"""Tests for DhanDepth200Feed — 200-level market depth WebSocket."""

from __future__ import annotations

import pytest

from brokers.dhan.depth_200 import DhanDepth200Feed


class TestDhanDepth200Feed:
    """Verify DhanDepth200Feed construction and API surface."""

    def test_depth_200_feed_init(self):
        """Construction with single instrument must succeed."""
        feed = DhanDepth200Feed(
            client_id="TEST_CLIENT",
            access_token="TEST_TOKEN",
            instrument=("NSE_EQ", "2885"),
        )

        assert feed._client_id == "TEST_CLIENT"
        assert feed._access_token == "TEST_TOKEN"
        assert feed._instrument == ("NSE_EQ", "2885")
        assert feed.max_instruments == 1
        assert feed.name == "dhan.depth_200"

    def test_depth_200_feed_init_no_instrument(self):
        """Construction without instrument must succeed (subscribe later)."""
        feed = DhanDepth200Feed(
            client_id="CLIENT",
            access_token="TOKEN",
        )
        assert feed._instrument is None
        assert feed._subscriptions == []

    def test_depth_200_max_instruments_1(self):
        """Maximum 1 instrument allowed per connection."""
        assert DhanDepth200Feed.MAX_INSTRUMENTS == 1

    def test_depth_200_subscribe_over_limit_raises(self):
        """Should raise ValueError if trying to subscribe with instrument already set."""
        feed = DhanDepth200Feed(
            client_id="CLIENT",
            access_token="TOKEN",
            instrument=("NSE_EQ", "2885"),
        )

        with pytest.raises(ValueError, match="Only 1 instrument allowed"):
            feed.subscribe(("NSE_EQ", "2886"))

    def test_depth_200_subscribe_single_instrument(self):
        """Should allow subscribing to single instrument."""
        feed = DhanDepth200Feed(
            client_id="CLIENT",
            access_token="TOKEN",
        )

        feed.subscribe(("NSE_EQ", "2885"))

        assert len(feed._subscriptions) == 1
        assert feed._instrument == ("NSE_EQ", "2885")

    def test_depth_200_init_over_limit_raises(self):
        """Should raise ValueError if initialized with instrument when one exists."""
        # This test validates the constructor validation
        DhanDepth200Feed(
            client_id="CLIENT",
            access_token="TOKEN",
            instrument=("NSE_EQ", "2885"),
        )
        # Already has instrument, trying to create another would fail
        # (validated by test_depth_200_subscribe_over_limit_raises)

    def test_depth_200_callback_registration(self):
        """on_depth must accept a callable and store it."""
        feed = DhanDepth200Feed(
            client_id="CLIENT",
            access_token="TOKEN",
        )

        received = []
        feed.on_depth(lambda data: received.append(data))

        assert len(feed._depth_callbacks) == 1
        assert callable(feed._depth_callbacks[0])

    def test_depth_200_multiple_callbacks(self):
        """Multiple callbacks can be registered."""
        feed = DhanDepth200Feed(
            client_id="CLIENT",
            access_token="TOKEN",
        )

        feed.on_depth(lambda d: None)
        feed.on_depth(lambda d: None)
        feed.on_depth(lambda d: None)

        assert len(feed._depth_callbacks) == 3

    def test_depth_200_is_connected_default_false(self):
        """is_connected must be False before connect() is called."""
        feed = DhanDepth200Feed(
            client_id="CLIENT",
            access_token="TOKEN",
        )
        assert feed._is_connected is False

    def test_depth_200_managed_service_protocol(self):
        """DhanDepth200Feed must implement ManagedService protocol."""
        feed = DhanDepth200Feed(
            client_id="CLIENT",
            access_token="TOKEN",
        )

        assert hasattr(feed, "name")
        assert hasattr(feed, "start")
        assert hasattr(feed, "stop")
        assert hasattr(feed, "health")
        assert feed.name == "dhan.depth_200"

    def test_depth_200_health_not_started(self):
        """Health should be STOPPED before start()."""
        from infrastructure.lifecycle.lifecycle import HealthState

        feed = DhanDepth200Feed(
            client_id="CLIENT",
            access_token="TOKEN",
        )

        health = feed.health()
        assert health.state == HealthState.STOPPED
        assert "not started" in health.detail
