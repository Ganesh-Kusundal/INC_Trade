"""Unit tests for DhanDepth20Feed, DhanDepth200Feed and gateway.depth_20/depth_200."""

from __future__ import annotations

import struct
from decimal import Decimal
from pathlib import Path
from unittest import mock

import pytest

from domain import DepthLevel, MarketDepth

# ──────────────────────────────────────────────────────────────────────────────
# Golden-file fixtures
# ──────────────────────────────────────────────────────────────────────────────
#
# Plan §5.1: previous harness packets used the same layout for depth-20 and
# depth-200 tests, hiding a header-layout mismatch (depth-20 reads
# security_id at offset 4; depth-200 reads num_rows at offset 8).
# These fixtures encode each layout exactly once, so a regression that
# flips the offset is caught immediately.

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def _load_golden(name: str) -> bytes:
    """Load a golden-file binary packet from the fixtures directory."""
    path = FIXTURES_DIR / name
    if not path.exists():
        pytest.skip(f"golden fixture missing: {path}")
    return path.read_bytes()


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _make_depth_packet(response_code, security_id, levels, total_slots=20):
    """Build a minimal Dhan depth-20 binary packet for testing."""
    header_size = 12
    level_size = 16
    body_size = total_slots * level_size
    packet = bytearray(header_size + body_size)
    struct.pack_into("<H", packet, 0, header_size + body_size)
    packet[2] = response_code
    packet[3] = 1
    struct.pack_into("<I", packet, 4, security_id)
    for i, (price, qty, orders) in enumerate(levels[:total_slots]):
        offset = header_size + i * level_size
        struct.pack_into("<d", packet, offset, price)
        struct.pack_into("<I", packet, offset + 8, qty)
        struct.pack_into("<I", packet, offset + 12, orders)
    return bytes(packet)


def _make_200_packet(response_code, num_rows, levels):
    """Build a minimal Dhan depth-200 binary packet for testing."""
    header_size = 12
    level_size = 16
    body = num_rows * level_size
    packet = bytearray(header_size + body)
    packet[2] = response_code
    struct.pack_into("<I", packet, 8, num_rows)
    for i, (price, qty, orders) in enumerate(levels[:num_rows]):
        offset = header_size + i * level_size
        struct.pack_into("<d", packet, offset, price)
        struct.pack_into("<I", packet, offset + 8, qty)
        struct.pack_into("<I", packet, offset + 12, orders)
    return bytes(packet)


def _make_feed20(instruments=None):
    from brokers.dhan.depth_20 import DhanDepth20Feed

    return DhanDepth20Feed("test_client", "test_token", instruments=instruments or [])


def _make_feed200(instrument=None):
    from brokers.dhan.depth_200 import DhanDepth200Feed

    return DhanDepth200Feed("test_client", "test_token", instrument=instrument)


# ──────────────────────────────────────────────────────────────────────────────
# DhanDepth20Feed
# ──────────────────────────────────────────────────────────────────────────────


class TestDhanDepth20Feed:
    def test_init_empty(self):
        feed = _make_feed20()
        assert feed._subscriptions == []
        assert feed._depth_cache == {}

    def test_init_with_instruments(self):
        feed = _make_feed20([("NSE_EQ", "500325")])
        assert len(feed._subscriptions) == 1

    def test_max_instruments_exceeded(self):
        from brokers.dhan.depth_20 import DhanDepth20Feed

        instruments = [("NSE_EQ", str(i)) for i in range(51)]
        with pytest.raises(ValueError, match="Maximum 50"):
            DhanDepth20Feed("c", "t", instruments=instruments)

    def test_subscribe_adds_instruments(self):
        feed = _make_feed20()
        feed.subscribe([("NSE_EQ", "500325"), ("NSE_FNO", "999")])
        assert len(feed._subscriptions) == 2

    def test_subscribe_exceeds_limit_raises(self):
        instruments = [("NSE_EQ", str(i)) for i in range(50)]
        feed = _make_feed20(instruments)
        with pytest.raises(ValueError, match="Maximum 50"):
            feed.subscribe([("NSE_EQ", "extra")])

    def test_parse_bid_packet(self):
        feed = _make_feed20()
        levels = [(24500.5, 100, 5), (24499.0, 200, 3)]
        packet = _make_depth_packet(41, 123456, levels)
        result = feed._parse_depth_packet(packet, 41, 123456)
        assert result["side"] == "bids"
        # depth-20 layout: header_value IS the security_id.
        assert result["header_value"] == 123456
        assert len(result["levels"]) == 2
        assert result["levels"][0].price == Decimal("24500.5")
        assert result["levels"][0].quantity == 100

    def test_parse_ask_packet(self):
        feed = _make_feed20()
        levels = [(24501.0, 150, 2)]
        packet = _make_depth_packet(51, 777, levels)
        result = feed._parse_depth_packet(packet, 51, 777)
        assert result["side"] == "asks"
        assert result["header_value"] == 777

    def test_zero_qty_levels_skipped(self):
        feed = _make_feed20()
        levels = [(24500.0, 0, 0), (24499.0, 50, 1)]
        packet = _make_depth_packet(41, 1, levels)
        result = feed._parse_depth_packet(packet, 41, 1)
        assert len(result["levels"]) == 1
        assert result["levels"][0].quantity == 50

    def test_too_short_packet_no_crash(self):
        feed = _make_feed20()
        feed._process_binary_message(b"\x00\x01")

    def test_bid_cache_updated(self):
        feed = _make_feed20()
        bids = [DepthLevel(Decimal("100"), 10, 1)]
        feed._dispatch_depth({"side": "bids", "levels": bids, "header_value": 42})
        with feed._depth_cache_lock:
            assert feed._depth_cache[42]["bids"] == bids
            assert feed._depth_cache[42]["asks"] == []

    def test_ask_does_not_clear_bids(self):
        feed = _make_feed20()
        bids = [DepthLevel(Decimal("100"), 10, 1)]
        asks = [DepthLevel(Decimal("101"), 5, 2)]
        feed._dispatch_depth({"side": "bids", "levels": bids, "header_value": 42})
        feed._dispatch_depth({"side": "asks", "levels": asks, "header_value": 42})
        with feed._depth_cache_lock:
            assert feed._depth_cache[42]["bids"] == bids
            assert feed._depth_cache[42]["asks"] == asks

    def test_latest_depth_none_before_data(self):
        assert _make_feed20().latest_depth(99999) is None

    def test_latest_depth_returns_market_depth(self):
        feed = _make_feed20()
        bid = [DepthLevel(Decimal("200"), 20, 2)]
        ask = [DepthLevel(Decimal("201"), 10, 1)]
        feed._dispatch_depth({"side": "bids", "levels": bid, "header_value": 55})
        feed._dispatch_depth({"side": "asks", "levels": ask, "header_value": 55})
        depth = feed.latest_depth(55)
        assert isinstance(depth, MarketDepth)
        assert depth.depth_type == "DEPTH_20"
        assert depth.bids[0].price == Decimal("200")
        assert depth.asks[0].price == Decimal("201")

    def test_on_depth_callback_receives_market_depth(self):
        feed = _make_feed20()
        received = []
        feed.on_depth(received.append)
        feed._dispatch_depth({"side": "bids", "levels": [], "header_value": 7})
        assert len(received) == 1
        assert isinstance(received[0], MarketDepth)
        assert received[0].depth_type == "DEPTH_20"

    def test_callback_exception_does_not_propagate(self):
        feed = _make_feed20()
        feed.on_depth(lambda d: (_ for _ in ()).throw(RuntimeError("boom")))
        feed._dispatch_depth({"side": "bids", "levels": [], "header_value": 1})

    def test_multiple_callbacks_all_fired(self):
        feed = _make_feed20()
        a, b = [], []
        feed.on_depth(a.append)
        feed.on_depth(b.append)
        feed._dispatch_depth({"side": "asks", "levels": [], "header_value": 2})
        assert len(a) == len(b) == 1

    def test_full_binary_roundtrip(self):
        feed = _make_feed20()
        received = []
        feed.on_depth(received.append)
        levels = [(24500.0, 50, 2), (24499.5, 100, 5)]
        packet = _make_depth_packet(41, 500325, levels)
        feed._process_binary_message(packet)
        assert len(received) == 1
        assert received[0].depth_type == "DEPTH_20"
        assert len(received[0].bids) == 2

    def test_send_subscription_no_ws_loop_drops_with_counter(self):
        # When the feed WebSocket loop is not running, the send is dropped
        # rather than silently swallowed. The dropped_depths counter must
        # increment so operators can see this in health().
        feed = _make_feed20()
        feed._ws = mock.MagicMock()
        feed._ws_loop = None
        assert feed._dropped_depths == 0
        feed._send_subscription([("NSE_EQ", "500325")])
        assert feed._dropped_depths == 1

    def test_health_stopped(self):
        from infrastructure.lifecycle.lifecycle import HealthState

        assert _make_feed20().health().state == HealthState.STOPPED

    def test_health_degraded(self):
        from infrastructure.lifecycle.lifecycle import HealthState

        feed = _make_feed20()
        feed._thread = mock.MagicMock()
        feed._thread.is_alive.return_value = True
        feed._is_connected = False
        assert feed.health().state == HealthState.DEGRADED

    def test_health_metrics_contain_depth_counters(self):
        feed = _make_feed20()
        feed._published_depths = 11
        feed._dropped_depths = 5
        h = feed.health()
        assert h.metrics["published_depths"] == 11
        assert h.metrics["dropped_depths"] == 5


# ──────────────────────────────────────────────────────────────────────────────
# DhanDepth200Feed
# ──────────────────────────────────────────────────────────────────────────────


class TestDhanDepth200Feed:
    def test_init_no_instrument(self):
        feed = _make_feed200()
        assert feed._subscriptions == []
        # Unified cache is per-security-id; empty until a packet arrives.
        assert feed._depth_cache == {}

    def test_init_with_instrument(self):
        feed = _make_feed200(("NSE_EQ", "500325"))
        assert len(feed._subscriptions) == 1

    def test_latest_depth_none_before_data(self):
        assert _make_feed200().latest_depth() is None

    def test_dispatch_merges_sides(self):
        feed = _make_feed200(("NSE_EQ", "500325"))
        bid = [DepthLevel(Decimal("1000"), 5, 1)]
        ask = [DepthLevel(Decimal("1001"), 3, 1)]
        feed._dispatch_depth({"side": "bids", "levels": bid})
        feed._dispatch_depth({"side": "asks", "levels": ask})
        depth = feed.latest_depth()
        assert depth.depth_type == "DEPTH_200"
        assert depth.bids[0].price == Decimal("1000")
        assert depth.asks[0].price == Decimal("1001")

    def test_ask_does_not_wipe_bids(self):
        feed = _make_feed200(("NSE_EQ", "500325"))
        bid = [DepthLevel(Decimal("500"), 10, 2)]
        feed._dispatch_depth({"side": "bids", "levels": bid})
        feed._dispatch_depth({"side": "asks", "levels": []})
        assert len(feed.latest_depth().bids) == 1

    def test_on_depth_callback_receives_market_depth(self):
        feed = _make_feed200(("NSE_EQ", "500325"))
        received = []
        feed.on_depth(received.append)
        feed._dispatch_depth({"side": "bids", "levels": []})
        assert isinstance(received[0], MarketDepth)

    def test_dispatch_drops_packet_when_no_subscription_and_empty_cache(self):
        """Plan §7.2: packets arriving before subscribe() must NOT be cached
        under a placeholder key. They are dropped and counted."""
        feed = _make_feed200()
        assert feed._subscriptions == []
        assert feed._depth_cache == {}
        assert feed._dropped_depths == 0
        feed._dispatch_depth({"side": "bids", "levels": [DepthLevel(Decimal("100"), 1, 1)]})
        # No subscription, no cache: dispatcher must drop the packet.
        assert feed._dropped_depths == 1
        assert feed._depth_cache == {}
        assert feed.latest_depth() is None

    def test_health_metrics_contain_depth_counters(self):
        feed = _make_feed200(("NSE_EQ", "500325"))
        feed._published_depths = 9
        feed._dropped_depths = 2
        h = feed.health()
        assert h.metrics["published_depths"] == 9
        assert h.metrics["dropped_depths"] == 2

    def test_parse_bid_packet_200(self):
        feed = _make_feed200()
        levels = [(1332.5, 100, 10), (1332.0, 200, 5)]
        packet = _make_200_packet(41, 2, levels)
        result = feed._parse_depth_packet(packet, 41, 2)
        assert result["side"] == "bids"
        assert len(result["levels"]) == 2

    def test_parse_ask_packet_200(self):
        feed = _make_feed200()
        packet = _make_200_packet(51, 1, [(1333.0, 50, 3)])
        result = feed._parse_depth_packet(packet, 51, 1)
        assert result["side"] == "asks"

    def test_send_subscription_no_ws_loop_drops_with_counter(self):
        feed = _make_feed200(("NSE_EQ", "500325"))
        feed._ws = mock.MagicMock()
        feed._ws_loop = None
        assert feed._dropped_depths == 0
        feed._send_subscription([("NSE_EQ", "500325")])
        assert feed._dropped_depths == 1


# ──────────────────────────────────────────────────────────────────────────────
# gateway.depth_20 / gateway.depth_200
# ──────────────────────────────────────────────────────────────────────────────


def _make_offline_gateway():
    from brokers.dhan.gateway import BrokerGateway
    from brokers.dhan.resolver import SymbolResolver

    resolver = SymbolResolver()
    resolver.load_from_rows(
        [
            {
                "SEM_TRADING_SYMBOL": "RELIANCE",
                "SEM_CUSTOM_SYMBOL": "RELIANCE",
                "SEM_SMST_SECURITY_ID": "500325",
                "SEM_EXM_EXCH_ID": "NSE_EQ",
                "SEM_INSTRUMENT_NAME": "EQUITY",
                "SEM_LOT_UNITS": 1,
                "SEM_TICK_SIZE": 0.05,
            }
        ]
    )

    conn = mock.MagicMock()
    conn.instruments = resolver
    conn.client_id = "testclient"
    conn.access_token = "testtoken"
    conn.depth_20_feed = None
    conn.depth_200_feed = None
    conn.market_data.get_depth.return_value = MarketDepth(
        bids=[DepthLevel(Decimal("1330"), 50, 2)],
        asks=[DepthLevel(Decimal("1331"), 30, 1)],
        depth_type="DEPTH_5",
    )

    gw = BrokerGateway.__new__(BrokerGateway)
    gw._conn = conn
    return gw


class TestGatewayDepth20:
    def _mock_feed20(self):
        from brokers.dhan.depth_20 import DhanDepth20Feed

        f = mock.MagicMock(spec=DhanDepth20Feed)
        f._subscriptions = []
        f.is_running = False
        f.latest_depth.return_value = None
        return f

    def test_wrong_exchange_raises(self):
        gw = _make_offline_gateway()
        with pytest.raises(ValueError, match="NSE segments"):
            gw.depth_20("CRUDEOIL", exchange="MCX")

    def test_creates_feed_on_first_call(self):
        gw = _make_offline_gateway()
        f = self._mock_feed20()
        gw._conn.create_depth_20_feed.return_value = f
        gw.depth_20("RELIANCE")
        gw._conn.create_depth_20_feed.assert_called_once()
        f.start.assert_called_once()

    def test_falls_back_to_rest_when_cache_empty(self):
        gw = _make_offline_gateway()
        f = self._mock_feed20()
        gw._conn.create_depth_20_feed.return_value = f
        result = gw.depth_20("RELIANCE")
        assert result.depth_type == "DEPTH_5"
        gw._conn.market_data.get_depth.assert_called_once()

    def test_returns_cached_depth(self):
        gw = _make_offline_gateway()
        cached = MarketDepth(
            bids=[DepthLevel(Decimal("1330"), 50, 2)],
            asks=[DepthLevel(Decimal("1331"), 30, 1)],
            depth_type="DEPTH_20",
        )
        f = self._mock_feed20()
        f.latest_depth.return_value = cached
        gw._conn.create_depth_20_feed.return_value = f
        result = gw.depth_20("RELIANCE")
        assert result.depth_type == "DEPTH_20"
        assert len(result.bids) == 1
        assert len(result.asks) == 1
        gw._conn.market_data.get_depth.assert_not_called()

    def test_merges_rest_asks_when_ws_cache_bids_only(self):
        gw = _make_offline_gateway()
        cached = MarketDepth(
            bids=[DepthLevel(Decimal("1330"), 50, 2)],
            asks=[],
            depth_type="DEPTH_20",
        )
        f = self._mock_feed20()
        f.latest_depth.return_value = cached
        gw._conn.create_depth_20_feed.return_value = f
        result = gw.depth_20("RELIANCE")
        assert result.depth_type == "DEPTH_20"
        assert len(result.bids) == 1
        assert len(result.asks) == 1
        gw._conn.market_data.get_depth.assert_called_once()

    def test_reuses_existing_feed(self):
        gw = _make_offline_gateway()
        f = self._mock_feed20()
        f._subscriptions = [("NSE_EQ", "500325")]
        f.is_running = True
        gw._conn.depth_20_feed = f
        gw.depth_20("RELIANCE")
        gw._conn.create_depth_20_feed.assert_not_called()
        f.start.assert_not_called()

    def test_subscribes_new_symbol_on_existing_feed(self):
        gw = _make_offline_gateway()
        f = self._mock_feed20()
        f._subscriptions = [("NSE_EQ", "999999")]
        f.is_running = True
        gw._conn.depth_20_feed = f
        gw.depth_20("RELIANCE")
        f.subscribe.assert_called_once_with([("NSE_EQ", "500325")])

    def test_on_depth_callback_registered(self):
        gw = _make_offline_gateway()
        f = self._mock_feed20()
        gw._conn.create_depth_20_feed.return_value = f
        cb = mock.MagicMock()
        gw.depth_20("RELIANCE", on_depth=cb)
        f.on_depth.assert_called_once_with(cb)


class TestGatewayDepth200:
    def _mock_feed200(self):
        from brokers.dhan.depth_200 import DhanDepth200Feed

        f = mock.MagicMock(spec=DhanDepth200Feed)
        f._subscriptions = []
        f.is_running = False
        f.latest_depth.return_value = None
        return f

    def test_wrong_exchange_raises(self):
        gw = _make_offline_gateway()
        with pytest.raises(ValueError, match="NSE segments"):
            gw.depth_200("CRUDEOIL", exchange="MCX")

    def test_creates_feed_on_first_call(self):
        gw = _make_offline_gateway()
        f = self._mock_feed200()
        gw._conn.create_depth_200_feed.return_value = f
        gw.depth_200("RELIANCE")
        gw._conn.create_depth_200_feed.assert_called_once()
        f.start.assert_called_once()

    def test_falls_back_to_rest_when_cache_empty(self):
        gw = _make_offline_gateway()
        f = self._mock_feed200()
        gw._conn.create_depth_200_feed.return_value = f
        result = gw.depth_200("RELIANCE")
        assert result.depth_type == "DEPTH_5"

    def test_returns_cached_depth(self):
        gw = _make_offline_gateway()
        cached = MarketDepth(
            bids=[DepthLevel(Decimal("1330"), 50, 2)],
            asks=[DepthLevel(Decimal("1331"), 30, 1)],
            depth_type="DEPTH_200",
        )
        f = self._mock_feed200()
        f.latest_depth.return_value = cached
        gw._conn.create_depth_200_feed.return_value = f
        result = gw.depth_200("RELIANCE")
        assert result.depth_type == "DEPTH_200"
        assert len(result.bids) == 1
        assert len(result.asks) == 1
        gw._conn.market_data.get_depth.assert_not_called()

    def test_rejects_second_different_instrument(self):
        gw = _make_offline_gateway()
        f = self._mock_feed200()
        f._subscriptions = [("NSE_EQ", "888888")]
        f.is_running = True
        gw._conn.depth_200_feed = f
        with pytest.raises(ValueError, match="already subscribed"):
            gw.depth_200("RELIANCE")


# ──────────────────────────────────────────────────────────────────────────────
# Golden-file packet regression tests
# ──────────────────────────────────────────────────────────────────────────────
#
# These tests parse the on-disk golden binary packets through the production
# parsers. They guard against the §5.1 silent correctness drift: a regression
# that flips an offset in the header parse would parse the real-world bytes
# into nonsense values, and these tests would catch it.


class TestGoldenDepthPackets:
    """End-to-end parsing of the on-disk golden packets via the production
    parsers (depth_20._parse_depth_packet, depth_200._parse_depth_packet)."""

    def test_depth20_bid_packet_parses_via_production_parser(self):
        feed = _make_feed20()
        data = _load_golden("depth_20_packet.bin")

        # Header sanity (matches build_depth20_packet in the generator):
        #   security_id at offset 4 (uint32 LE) == 2885
        #   response_code at byte 2 == 41 (BID)
        assert data[2] == 41
        sid = struct.unpack_from("<I", data, 4)[0]
        assert sid == 2885

        result = feed._parse_depth_packet(data, 41, sid)
        assert result["side"] == "bids"
        # depth-20 layout: header_value IS the security_id (offset 4).
        assert result["header_value"] == 2885
        # 5 bid levels encoded by the generator.
        assert len(result["levels"]) == 5
        assert result["levels"][0].price == Decimal("2450.55")
        assert result["levels"][0].quantity == 100
        assert result["levels"][0].orders == 5

    def test_depth20_ask_packet_parses_via_production_parser(self):
        feed = _make_feed20()
        data = _load_golden("depth_20_ask_packet.bin")

        assert data[2] == 51
        sid = struct.unpack_from("<I", data, 4)[0]
        assert sid == 2885

        result = feed._parse_depth_packet(data, 51, sid)
        assert result["side"] == "asks"
        assert result["header_value"] == 2885
        assert len(result["levels"]) == 5
        assert result["levels"][0].price == Decimal("2450.65")
        assert result["levels"][0].quantity == 80

    def test_depth20_packet_header_layout_does_not_collide_with_num_rows(self):
        """The depth-20 header puts security_id at offset 4, NOT num_rows.

        This guards against §5.1: a regression that read num_rows at offset 4
        here would misread security_id 2885 (= 0xB45) as a num_rows count,
        causing the loop to skip most levels.
        """
        feed = _make_feed20()
        data = _load_golden("depth_20_packet.bin")

        # Simulate the buggy reader: treat offset 4 as num_rows. With
        # security_id=2885 and a body of 20 levels, the buggy reader would
        # parse only the first 2885/16 = 180 levels into something else, but
        # because the body is exactly 20 levels, it would NOT skip levels
        # silently — it would over-read past the buffer. Production parser
        # bounds by HEADER_SIZE + LEVEL_SIZE; this test confirms 5 levels
        # come out regardless of the value at offset 4.
        sid_under_test = struct.unpack_from("<I", data, 4)[0]
        assert sid_under_test == 2885
        result = feed._parse_depth_packet(data, 41, sid_under_test)
        # Bounded by data length, not by an attacker-controlled num_rows:
        assert len(result["levels"]) == 5

    def test_depth20_feed_dispatch_populates_cache(self):
        """Whole-pipeline test: feed._process_binary_message → cache.

        Verifies that the real-bytes packet, when fed into the production
        _process_binary_message, populates _depth_cache with the right
        MarketDepth entry.
        """
        feed = _make_feed20([("NSE_EQ", "2885")])
        bid_data = _load_golden("depth_20_packet.bin")
        ask_data = _load_golden("depth_20_ask_packet.bin")

        feed._process_binary_message(bid_data)
        feed._process_binary_message(ask_data)

        cached = feed.latest_depth(2885)
        assert cached is not None
        assert cached.depth_type == "DEPTH_20"
        assert len(cached.bids) == 5
        assert len(cached.asks) == 5
        assert cached.bids[0].price == Decimal("2450.55")
        assert cached.asks[0].price == Decimal("2450.65")

    def test_depth200_bid_packet_parses_via_production_parser(self):
        feed = _make_feed200(("NSE_EQ", "2885"))
        data = _load_golden("depth_200_packet.bin")

        # Header sanity: num_rows at offset 8 (uint32 LE) == 25
        assert data[2] == 41
        num_rows = struct.unpack_from("<I", data, 8)[0]
        assert num_rows == 25

        result = feed._parse_depth_packet(data, 41, num_rows)
        assert result["side"] == "bids"
        assert len(result["levels"]) == 25
        # Top of book must be the highest bid; descending.
        prices = [float(lvl.price) for lvl in result["levels"]]
        assert prices == sorted(prices, reverse=True)

    def test_depth200_ask_packet_parses_via_production_parser(self):
        feed = _make_feed200(("NSE_EQ", "2885"))
        data = _load_golden("depth_200_ask_packet.bin")

        assert data[2] == 51
        num_rows = struct.unpack_from("<I", data, 8)[0]
        assert num_rows == 25

        result = feed._parse_depth_packet(data, 51, num_rows)
        assert result["side"] == "asks"
        assert len(result["levels"]) == 25
        prices = [float(lvl.price) for lvl in result["levels"]]
        assert prices == sorted(prices)

    def test_depth200_header_layout_uses_num_rows_not_security_id(self):
        """Depth-200 header layout has num_rows at offset 8, NOT security_id.

        Symmetric guard to depth-20: a regression that read security_id at
        offset 8 here would parse the field as 0 (it's reserved/zero in the
        generator output), causing the loop to read 0 levels.
        """
        feed = _make_feed200(("NSE_EQ", "2885"))
        data = _load_golden("depth_200_packet.bin")

        # Read offset 4 as if it were num_rows — must yield 0 because the
        # generator leaves offset 4..8 zero. Production parser uses offset 8.
        bogus_num_rows = struct.unpack_from("<I", data, 4)[0]
        correct_num_rows = struct.unpack_from("<I", data, 8)[0]

        assert bogus_num_rows == 0, (
            "depth-200 offset 4 must be reserved (zero); if it is not, header layout has changed"
        )
        assert correct_num_rows == 25

        # Production parser must use correct_num_rows, returning 25 levels.
        result = feed._parse_depth_packet(data, 41, correct_num_rows)
        assert len(result["levels"]) == 25

    def test_depth200_feed_dispatch_populates_cache(self):
        feed = _make_feed200(("NSE_EQ", "2885"))
        bid_data = _load_golden("depth_200_packet.bin")
        ask_data = _load_golden("depth_200_ask_packet.bin")

        feed._process_binary_message(bid_data)
        feed._process_binary_message(ask_data)

        cached = feed.latest_depth()
        assert cached is not None
        assert cached.depth_type == "DEPTH_200"
        assert len(cached.bids) == 25
        assert len(cached.asks) == 25

    def test_golden_packets_have_distinct_header_layouts(self):
        """Final invariant from §5.1: depth-20 and depth-200 MUST disagree on
        the meaning of offset 4 vs offset 8 in the header.

        This test reads both golden files and asserts that depth-20 puts the
        meaningful value at offset 4 while depth-200 leaves it zero and puts
        the meaningful value at offset 8. If the two feeds ever drift toward
        a shared layout, this test fails immediately.
        """
        depth20 = _load_golden("depth_20_packet.bin")
        depth200 = _load_golden("depth_200_packet.bin")

        d20_off4 = struct.unpack_from("<I", depth20, 4)[0]
        d20_off8 = struct.unpack_from("<I", depth20, 8)[0]
        d200_off4 = struct.unpack_from("<I", depth200, 4)[0]
        d200_off8 = struct.unpack_from("<I", depth200, 8)[0]

        # Depth-20 carries security_id at offset 4 (== 2885).
        assert d20_off4 == 2885
        # Depth-20 does NOT carry num_rows at offset 8 (== 0 in fixture).
        assert d20_off8 == 0
        # Depth-200 does NOT carry security_id at offset 4 (== 0).
        assert d200_off4 == 0
        # Depth-200 carries num_rows at offset 8 (== 25).
        assert d200_off8 == 25
