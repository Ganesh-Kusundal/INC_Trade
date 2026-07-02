"""Unit tests for strict-mode ``_publish_tick`` (Plan §7.7).

The legacy ``_publish_tick`` silently substituted ``Decimal("0")`` for any
missing field, allowing malformed packets to surface as zero-LTP ticks
that downstream subscribers could mistake for real signals. The strict
mode drops such events and increments a counter that ``health()`` exposes.

These tests pin the behaviour so a regression that re-introduces the silent
zero-default is caught immediately.
"""

from __future__ import annotations

from decimal import Decimal
from unittest import mock

from brokers.dhan.websocket import DhanMarketFeed


def _make_feed(event_bus=None) -> DhanMarketFeed:
    """Build a DhanMarketFeed with the SDK and resolver stubbed out."""
    import threading

    feed = DhanMarketFeed.__new__(DhanMarketFeed)
    # Bypass __init__ (the SDK needs real credentials). Wire only the
    # attributes that ``_publish_tick`` / ``_publish_depth`` and
    # ``health`` read.
    feed._event_bus = event_bus
    feed._published_ticks = 0
    feed._dropped_ticks = 0
    feed._published_depths = 0
    feed._dropped_depths = 0
    feed._thread = None
    feed._reconnect_count = 0
    feed._last_message_at = None
    feed._lock = threading.RLock()
    feed._is_connected = False
    return feed


# ── Happy path ─────────────────────────────────────────────────────────────


class TestPublishTickHappyPath:
    def test_publishes_when_ltp_is_positive(self):
        bus = mock.MagicMock()
        feed = _make_feed(event_bus=bus)
        feed._publish_tick(
            {
                "symbol": "RELIANCE",
                "ltp": Decimal("2450.55"),
                "open": Decimal("2440"),
                "high": Decimal("2460"),
                "low": Decimal("2435"),
                "close": Decimal("2445"),
                "volume": 1000,
                "change": Decimal("5.55"),
            }
        )
        bus.publish.assert_called_once()
        assert feed._published_ticks == 1
        assert feed._dropped_ticks == 0

    def test_zero_ohlc_is_acceptable_for_fresh_listing(self):
        """OHLC == 0 is legal for a freshly-listed symbol; only LTP == 0 drops."""
        bus = mock.MagicMock()
        feed = _make_feed(event_bus=bus)
        feed._publish_tick(
            {
                "symbol": "NEWLIST",
                "ltp": Decimal("100"),
                "open": Decimal("0"),
                "high": Decimal("0"),
                "low": Decimal("0"),
                "close": Decimal("0"),
            }
        )
        bus.publish.assert_called_once()
        assert feed._published_ticks == 1


# ── Drop cases (the strict-mode rules) ─────────────────────────────────────


class TestPublishTickStrictModeDrops:
    def test_drops_when_ltp_missing(self):
        bus = mock.MagicMock()
        feed = _make_feed(event_bus=bus)
        feed._publish_tick({"symbol": "RELIANCE"})
        bus.publish.assert_not_called()
        assert feed._dropped_ticks == 1
        assert feed._published_ticks == 0

    def test_drops_when_ltp_is_zero(self):
        bus = mock.MagicMock()
        feed = _make_feed(event_bus=bus)
        feed._publish_tick({"symbol": "RELIANCE", "ltp": Decimal("0")})
        bus.publish.assert_not_called()
        assert feed._dropped_ticks == 1
        assert feed._published_ticks == 0

    def test_drops_when_ltp_is_zero_int(self):
        """An int 0 must also be dropped (legacy code path produced this)."""
        bus = mock.MagicMock()
        feed = _make_feed(event_bus=bus)
        feed._publish_tick({"symbol": "RELIANCE", "ltp": 0})
        bus.publish.assert_not_called()
        assert feed._dropped_ticks == 1

    def test_drops_when_symbol_missing(self):
        bus = mock.MagicMock()
        feed = _make_feed(event_bus=bus)
        feed._publish_tick({"ltp": Decimal("100")})
        bus.publish.assert_not_called()
        assert feed._dropped_ticks == 1

    def test_drops_when_symbol_is_empty_string(self):
        bus = mock.MagicMock()
        feed = _make_feed(event_bus=bus)
        feed._publish_tick({"symbol": "", "ltp": Decimal("100")})
        bus.publish.assert_not_called()
        assert feed._dropped_ticks == 1

    def test_dropped_counter_accumulates_across_calls(self):
        bus = mock.MagicMock()
        feed = _make_feed(event_bus=bus)
        for _ in range(7):
            feed._publish_tick({"symbol": "X", "ltp": Decimal("0")})
        assert feed._dropped_ticks == 7
        assert feed._published_ticks == 0


# ── No event bus configured ────────────────────────────────────────────────


class TestPublishTickNoBus:
    def test_publish_tick_is_silent_when_no_event_bus(self):
        feed = _make_feed(event_bus=None)
        # Must not raise; must not increment counters either (the drop
        # counter only tracks the strict-mode rule, not "no bus").
        feed._publish_tick({"symbol": "X", "ltp": Decimal("100")})
        assert feed._published_ticks == 0
        assert feed._dropped_ticks == 0


# ── health() exposes the counters (Plan §7.7) ──────────────────────────────


class TestHealthExposesTickCounters:
    def test_health_metrics_contain_published_and_dropped(self):
        feed = _make_feed(event_bus=None)
        feed._published_ticks = 12
        feed._dropped_ticks = 3
        h = feed.health()
        assert h.metrics["published_ticks"] == 12
        assert h.metrics["dropped_ticks"] == 3

    def test_health_metrics_initialise_to_zero(self):
        feed = _make_feed(event_bus=None)
        h = feed.health()
        assert h.metrics["published_ticks"] == 0
        assert h.metrics["dropped_ticks"] == 0
