"""Unit tests for BinaryDepthFeed in depth_feed_base.py."""

from __future__ import annotations

import struct
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from inc_trade.domain.lifecycle_health import HealthState, HealthStatus

from brokers.adapters.dhan.depth_feed_base import (
    _HEADER_SIZE,
    _LEVEL_SIZE,
    BinaryDepthFeed,
)


def _build_depth_packet(
    response_code: int,
    security_id: int,
    levels: list[tuple[float, int, int]],
) -> bytes:
    """Build a binary depth packet with a 12-byte header and 16-byte levels.

    Header: response_code(1 byte) + padding(3 bytes) + security_id(4 bytes) + length(4 bytes)
    Level: price(8 bytes double) + quantity(4 bytes uint32) + orders(4 bytes uint32)
    """
    header = struct.pack(
        "<B3sII",
        response_code,
        b"\x00\x00\x00",
        security_id,
        len(levels) * _LEVEL_SIZE,
    )
    body = b""
    for price, qty, orders in levels:
        body += struct.pack("<dII", price, qty, orders)
    return header + body


@pytest.fixture
def depth_feed() -> BinaryDepthFeed:
    """Create a BinaryDepthFeed instance for testing."""
    return BinaryDepthFeed(
        client_id="test_client",
        access_token="test_token",
        endpoint="wss://test.example.com",
        request_code=23,
        total_slots=20,
        subs_per_connection=50,
        depth_type="DEPTH_20",
        name="test_depth_feed",
        event_name="depth_update",
        header_carries_security_id=True,
    )


class TestBinaryDepthFeedInit:
    """Tests for BinaryDepthFeed.__init__."""

    def test_initial_subscriptions_empty(self, depth_feed: BinaryDepthFeed) -> None:
        assert depth_feed._subscriptions == []

    def test_initial_is_not_running(self, depth_feed: BinaryDepthFeed) -> None:
        assert depth_feed.is_running is False

    def test_initial_thread_is_none(self, depth_feed: BinaryDepthFeed) -> None:
        assert depth_feed._thread is None

    def test_initial_depth_cache_empty(self, depth_feed: BinaryDepthFeed) -> None:
        assert depth_feed._depth_cache == {}

    def test_initial_counters_zero(self, depth_feed: BinaryDepthFeed) -> None:
        assert depth_feed._published_depths == 0
        assert depth_feed._dropped_depths == 0

    def test_config_stored(self, depth_feed: BinaryDepthFeed) -> None:
        assert depth_feed.ENDPOINT == "wss://test.example.com"
        assert depth_feed.REQUEST_CODE == 23
        assert depth_feed.total_slots == 20
        assert depth_feed.subs_per_connection == 50
        assert depth_feed.DEPTH_TYPE == "DEPTH_20"
        assert depth_feed.name == "test_depth_feed"
        assert depth_feed.EVENT_NAME == "depth_update"
        assert depth_feed.header_carries_security_id is True

    def test_backward_compat_aliases(self, depth_feed: BinaryDepthFeed) -> None:
        assert depth_feed.MAX_INSTRUMENTS == 50
        assert depth_feed.TOTAL_DEPTH_PACKETS == 20


class TestParseDepthPacket:
    """Tests for BinaryDepthFeed._parse_depth_packet."""

    def test_valid_bid_packet(self, depth_feed: BinaryDepthFeed) -> None:
        levels = [(250000.0, 100, 5), (249900.0, 200, 3)]
        data = _build_depth_packet(41, 12345, levels)

        result = depth_feed._parse_depth_packet(data, 41, 12345)

        assert result["side"] == "bids"
        assert result["header_value"] == 12345
        assert len(result["levels"]) == 2
        assert result["levels"][0].price == Decimal("250000.0")
        assert result["levels"][0].quantity == 100
        assert result["levels"][0].orders == 5
        assert result["levels"][1].price == Decimal("249900.0")
        assert result["levels"][1].quantity == 200

    def test_valid_ask_packet(self, depth_feed: BinaryDepthFeed) -> None:
        levels = [(250100.0, 50, 2)]
        data = _build_depth_packet(51, 67890, levels)

        result = depth_feed._parse_depth_packet(data, 51, 67890)

        assert result["side"] == "asks"
        assert result["header_value"] == 67890
        assert len(result["levels"]) == 1
        assert result["levels"][0].price == Decimal("250100.0")
        assert result["levels"][0].quantity == 50

    def test_empty_data_returns_empty_levels(self, depth_feed: BinaryDepthFeed) -> None:
        data = _build_depth_packet(41, 12345, [])

        result = depth_feed._parse_depth_packet(data, 41, 12345)

        assert result["levels"] == []
        assert result["side"] == "bids"

    def test_short_data_stops_at_boundary(self, depth_feed: BinaryDepthFeed) -> None:
        data = _build_depth_packet(41, 12345, [(250000.0, 100, 5)])
        truncated = data[: _HEADER_SIZE + 8]

        result = depth_feed._parse_depth_packet(truncated, 41, 12345)

        assert result["levels"] == []

    def test_zero_quantity_excluded(self, depth_feed: BinaryDepthFeed) -> None:
        levels = [(250000.0, 0, 0), (249900.0, 100, 5)]
        data = _build_depth_packet(41, 12345, levels)

        result = depth_feed._parse_depth_packet(data, 41, 12345)

        assert len(result["levels"]) == 1
        assert result["levels"][0].quantity == 100

    def test_respects_total_slots_limit(self) -> None:
        feed = BinaryDepthFeed(
            client_id="c",
            access_token="t",
            endpoint="wss://x",
            request_code=23,
            total_slots=2,
            subs_per_connection=50,
            depth_type="DEPTH_20",
            name="n",
            event_name="e",
            header_carries_security_id=True,
        )
        levels = [(250000.0, 100, 1), (249900.0, 200, 2), (249800.0, 300, 3)]
        data = _build_depth_packet(41, 12345, levels)

        result = feed._parse_depth_packet(data, 41, 12345)

        assert len(result["levels"]) == 2


class TestSubscribe:
    """Tests for BinaryDepthFeed.subscribe."""

    def test_subscribe_adds_instrument(self, depth_feed: BinaryDepthFeed) -> None:
        depth_feed.subscribe([("NSE_EQ", "12345")])

        assert ("NSE_EQ", "12345") in depth_feed._subscriptions

    def test_subscribe_tuple_not_list(self, depth_feed: BinaryDepthFeed) -> None:
        depth_feed.subscribe(("NSE_EQ", "12345"))

        assert ("NSE_EQ", "12345") in depth_feed._subscriptions

    def test_subscribe_no_duplicates(self, depth_feed: BinaryDepthFeed) -> None:
        depth_feed.subscribe([("NSE_EQ", "12345")])
        depth_feed.subscribe([("NSE_EQ", "12345")])

        assert depth_feed._subscriptions.count(("NSE_EQ", "12345")) == 1

    def test_subscribe_exceeds_limit_raises(self, depth_feed: BinaryDepthFeed) -> None:
        instruments = [("NSE_EQ", str(i)) for i in range(51)]

        with pytest.raises(ValueError, match="Maximum 50"):
            depth_feed.subscribe(instruments)

    def test_subscribe_empty_list_noop(self, depth_feed: BinaryDepthFeed) -> None:
        depth_feed.subscribe([])

        assert depth_feed._subscriptions == []


class TestUnsubscribe:
    """Tests for BinaryDepthFeed unsubscribe behavior."""

    def test_unregister_removes_callback(self, depth_feed: BinaryDepthFeed) -> None:
        cb = MagicMock()
        depth_feed._depth_callbacks.append(cb)

        depth_feed._unregister_callback(depth_feed._depth_callbacks, cb)

        assert cb not in depth_feed._depth_callbacks


class TestHealth:
    """Tests for BinaryDepthFeed.health."""

    def test_health_returns_health_status(self, depth_feed: BinaryDepthFeed) -> None:
        result = depth_feed.health()

        assert isinstance(result, HealthStatus)
        assert result.service == "test_depth_feed"

    def test_health_stopped_when_no_thread(self, depth_feed: BinaryDepthFeed) -> None:
        result = depth_feed.health()

        assert result.state == HealthState.STOPPED
        assert result.detail == "not started"

    def test_health_includes_metrics(self, depth_feed: BinaryDepthFeed) -> None:
        result = depth_feed.health()

        assert "reconnect_count" in result.metrics
        assert "subscriptions" in result.metrics
        assert "depth_type" in result.metrics
        assert "published_depths" in result.metrics
        assert "dropped_depths" in result.metrics

    def test_health_metrics_update_with_subscriptions(
        self, depth_feed: BinaryDepthFeed
    ) -> None:
        depth_feed.subscribe([("NSE_EQ", "12345"), ("NSE_EQ", "67890")])

        result = depth_feed.health()

        assert result.metrics["subscriptions"] == 2


class TestConstants:
    """Tests for BinaryDepthFeed class constants."""

    def test_header_size(self) -> None:
        assert BinaryDepthFeed.HEADER_SIZE == 12

    def test_depth_level_size(self) -> None:
        assert BinaryDepthFeed.DEPTH_LEVEL_SIZE == 16

    def test_bid_response_code(self) -> None:
        assert BinaryDepthFeed.BID_RESPONSE_CODE == 41

    def test_ask_response_code(self) -> None:
        assert BinaryDepthFeed.ASK_RESPONSE_CODE == 51
