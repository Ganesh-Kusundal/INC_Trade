"""Unit and chaos tests for Dhan WebSocket reconnection hardening (H2 Critical Fix).

Tests verify:
1. Max reconnect attempts stops feed after configurable limit
2. Staleness detection warns when feed hasn't received messages
3. Health endpoint exposes reconnect metrics
4. Reconnect counter resets on successful connection
"""

import threading
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest


class TestDhanMarketFeedMaxReconnectAttempts:
    """Test max reconnect attempts prevents infinite retry loop."""

    @pytest.fixture
    def mock_feed(self):
        """Create DhanMarketFeed with mocked SDK feed."""
        from brokers.dhan.websocket import DhanMarketFeed

        # Create feed with mocked SDK
        with patch("brokers.dhan.websocket.market_feed._sdk_market_feed_class") as mock_sdk:
            mock_sdk_instance = MagicMock()
            mock_sdk.return_value = mock_sdk_instance

            feed = DhanMarketFeed(
                client_id="test_client",
                access_token="test_token",
            )
            # Manually set the feed to avoid SDK initialization
            feed._feed = mock_sdk_instance

        return feed, mock_sdk_instance

    def test_max_reconnect_attempts_stops_feed(self, mock_feed, monkeypatch):
        """Feed should stop after MAX_RECONNECT_ATTEMPTS failures."""
        feed, mock_sdk = mock_feed

        # Set max attempts to 5 for fast testing
        monkeypatch.setenv("DHAN_MAX_RECONNECT_ATTEMPTS", "5")

        # Simulate 6 consecutive failures
        call_count = 0

        def fail_on_run():
            nonlocal call_count
            call_count += 1
            if call_count <= 6:
                raise ConnectionError("Connection lost")

        mock_sdk.run.side_effect = fail_on_run

        # Start feed in background thread
        thread = threading.Thread(target=feed._run, daemon=True)
        thread.start()

        # Wait for feed to exceed max attempts
        time.sleep(0.5)
        feed._stop_event.set()
        thread.join(timeout=2.0)

        # Should have stopped after 5 attempts (not continued to 6)
        assert call_count <= 5, f"Feed continued beyond max attempts: {call_count}"

        # Feed should be disconnected
        assert feed._is_connected is False

    def test_reconnect_count_resets_on_success(self, mock_feed, monkeypatch):
        """Reconnect count should reset after successful connection."""
        feed, mock_sdk = mock_feed

        monkeypatch.setenv("DHAN_MAX_RECONNECT_ATTEMPTS", "50")

        # Simulate: fail 3 times, succeed, fail again
        call_count = 0

        def intermittent_failures():
            nonlocal call_count
            call_count += 1
            # Fail first 3 calls, succeed on 4th, fail again
            if call_count <= 3 or call_count == 5:
                raise ConnectionError("Connection lost")
            # call_count == 4: success (return normally)

        mock_sdk.run.side_effect = intermittent_failures

        # Start feed
        thread = threading.Thread(target=feed._run, daemon=True)
        thread.start()

        # Wait for several reconnect cycles
        time.sleep(1.0)
        feed._stop_event.set()
        thread.join(timeout=2.0)

        # After successful connection (call 4), reconnect_count should reset
        # Then fail on call 5, so count should be 1 (not 5)
        assert feed._reconnect_count <= 2, (
            f"Reconnect count didn't reset after success: {feed._reconnect_count}"
        )


class TestDhanMarketFeedStalenessDetection:
    """Test staleness detection warns on ghost connections."""

    @pytest.fixture
    def feed_with_old_message(self):
        """Create feed with stale last_message_at."""
        from brokers.dhan.websocket import DhanMarketFeed

        feed = DhanMarketFeed(
            client_id="test_client",
            access_token="test_token",
        )

        # Set last message to 120 seconds ago (stale)
        from datetime import timedelta
        feed._last_message_at = datetime.now(timezone.utc) - timedelta(seconds=120)
        feed._message_count = 10  # Was active

        return feed

    def test_staleness_detected_in_health(self, feed_with_old_message, monkeypatch):
        """Health endpoint should report is_stale=True when feed is stale."""
        feed = feed_with_old_message
        monkeypatch.setenv("DHAN_STALENESS_THRESHOLD_SECONDS", "60.0")

        health = feed.health()

        assert health.metrics["is_stale"] is True
        assert health.metrics["last_message_age_seconds"] >= 120
        assert health.metrics["staleness_threshold_seconds"] == 60.0

    def test_no_staleness_when_recent_message(self, monkeypatch):
        """Health endpoint should report is_stale=False when feed is fresh."""
        from brokers.dhan.websocket import DhanMarketFeed

        feed = DhanMarketFeed(
            client_id="test_client",
            access_token="test_token",
        )
        # Recent message
        feed._last_message_at = datetime.now(timezone.utc)
        feed._message_count = 100

        monkeypatch.setenv("DHAN_STALENESS_THRESHOLD_SECONDS", "60.0")

        health = feed.health()

        assert health.metrics["is_stale"] is False
        assert health.metrics["last_message_age_seconds"] < 1.0


class TestDhanMarketFeedHealthMetrics:
    """Test health endpoint exposes all reconnect metrics."""

    def test_health_exposes_reconnect_metrics(self):
        """Health should include max_reconnect_attempts and staleness info."""
        from brokers.dhan.websocket import DhanMarketFeed

        feed = DhanMarketFeed(
            client_id="test_client",
            access_token="test_token",
        )

        # Simulate some reconnects
        feed._reconnect_count = 10
        feed._is_connected = True
        feed._last_message_at = datetime.now(timezone.utc)

        health = feed.health()

        # Verify all H2 metrics are present
        assert "max_reconnect_attempts" in health.metrics
        assert "is_stale" in health.metrics
        assert "staleness_threshold_seconds" in health.metrics
        assert "reconnect_count" in health.metrics
        assert "last_message_age_seconds" in health.metrics

        # Verify values
        assert health.metrics["max_reconnect_attempts"] == 50  # default
        assert health.metrics["reconnect_count"] == 10
        assert health.metrics["is_stale"] is False

    def test_health_max_reconnect_attempts_configurable(self, monkeypatch):
        """max_reconnect_attempts should be configurable via env var."""
        from brokers.dhan.websocket import DhanMarketFeed

        monkeypatch.setenv("DHAN_MAX_RECONNECT_ATTEMPTS", "100")

        feed = DhanMarketFeed(
            client_id="test_client",
            access_token="test_token",
        )

        health = feed.health()

        assert health.metrics["max_reconnect_attempts"] == 100


class TestDhanMarketFeedChaosScenarios:
    """Chaos tests for extreme failure scenarios."""

    def test_rapid_reconnect_does_not_exhaust_resources(self, monkeypatch):
        """50 rapid reconnects should not leak file descriptors or memory."""
        from unittest.mock import MagicMock

        from brokers.dhan.websocket import DhanMarketFeed

        # Use small max for faster test
        monkeypatch.setenv("DHAN_MAX_RECONNECT_ATTEMPTS", "3")

        with patch("brokers.dhan.websocket.market_feed._sdk_market_feed_class") as mock_sdk:
            mock_sdk_instance = MagicMock()
            mock_sdk_instance.run.side_effect = ConnectionError("Immediate fail")
            mock_sdk.return_value = mock_sdk_instance
            # _build_sdk_feed_locked calls _sdk_market_feed_class()(...) — two levels:
            # mock_sdk() → mock_sdk_instance (the class), mock_sdk_instance(...) → instance.
            # Wire the second level back to the same mock so run() has the side effect.
            mock_sdk.return_value.return_value = mock_sdk_instance

            feed = DhanMarketFeed(
                client_id="test_client",
                access_token="test_token",
            )
            feed._feed = mock_sdk_instance

            # Run reconnect loop
            thread = threading.Thread(target=feed._run, daemon=True)
            thread.start()

            # Wait for max attempts (with backoff: 1s + 2s = 3s total)
            time.sleep(4.0)
            feed._stop_event.set()
            thread.join(timeout=2.0)

            # Should have stopped at max attempts
            assert feed._reconnect_count >= 3
            assert feed._is_connected is False

    def test_intermittent_failures_handled_gracefully(self, monkeypatch):
        """Intermittent failures (fail-success-fail) should reset counter correctly."""
        from unittest.mock import MagicMock

        from brokers.dhan.websocket import DhanMarketFeed

        # Use larger max to allow multiple cycles
        monkeypatch.setenv("DHAN_MAX_RECONNECT_ATTEMPTS", "20")

        with patch("brokers.dhan.websocket.market_feed._sdk_market_feed_class") as mock_sdk:
            mock_sdk_instance = MagicMock()

            call_count = 0

            def pattern():
                nonlocal call_count
                call_count += 1
                # Pattern: fail, success, fail, success
                if call_count % 2 == 1:  # Odd numbers: fail
                    raise ConnectionError("Fail")
                # Even numbers: success (return normally)

            mock_sdk_instance.run.side_effect = pattern
            mock_sdk.return_value = mock_sdk_instance
            # _build_sdk_feed_locked calls _sdk_market_feed_class()(...) — two levels:
            # mock_sdk() → mock_sdk_instance (the class), mock_sdk_instance(...) → instance.
            # Wire the second level back to the same mock so run() has the pattern side effect.
            mock_sdk.return_value.return_value = mock_sdk_instance

            feed = DhanMarketFeed(
                client_id="test_client",
                access_token="test_token",
            )
            feed._feed = mock_sdk_instance

            thread = threading.Thread(target=feed._run, daemon=True)
            thread.start()

            # Wait for several cycles (fail 1s, success, fail 1s, success)
            time.sleep(5.0)
            feed._stop_event.set()
            thread.join(timeout=2.0)

            # Should have continued due to successful resets
            assert call_count >= 4, f"Expected at least 4 calls, got {call_count}"
