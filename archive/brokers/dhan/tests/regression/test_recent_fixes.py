"""Regression tests locking in every fix applied in the June-2026 session.

These are all **offline / unit** tests — no live API calls.  They fail
immediately if a refactor reverts one of the six bug fixes:

Fix 1  — ``_complete_depth_snapshot``: gateway merges REST asks into WS depth
           when the WS cache has only bids (partial packet received first).
Fix 2  — ``_send_subscription`` uses ``_ws_loop`` not caller-thread loop:
           subscription sent from gateway thread must use the feed's loop.
Fix 3  — Rate-limit bucket map: ``_acquire_rate_limit_token`` hits the correct
           ``MultiBucketRateLimiter`` bucket (read→market_data, write→orders).
Fix 4  — SDK depth list→{bids, asks}: ``_normalize_sdk_depth`` converts the
           SDK list format ``[{bid_price, ask_price, ...}]`` to dict form.
Fix 5  — Bridge ``DEPTH_20`` symbol: events with ``symbol=None`` must use the
           ``depth.symbol`` field and all Decimal values serialised before JSON.
Fix 6  — Quote endpoint interval: ``/marketfeed/quote`` min interval is 1.0 s
           (Dhan documented limit), not 0.15 s.
"""

from __future__ import annotations

from decimal import Decimal
from unittest import mock

from brokers.dhan.http_client import (
    _RATE_LIMITS,
    _RL_BUCKET_MAP,
    _rate_limit_bucket,
)
from brokers.dhan.websocket.market_feed import DhanMarketFeed
from domain import DepthLevel, MarketDepth

# ---------------------------------------------------------------------------
# Fix 1 — _complete_depth_snapshot: REST merge for missing ask/bid sides
# ---------------------------------------------------------------------------

class TestCompleteDepthSnapshot:
    """gateway._complete_depth_snapshot merges REST fallback when a side is empty."""

    def _make_gateway(self):
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
                    "SEM_EXPIRY_DATE": "",
                }
            ]
        )
        conn = mock.MagicMock()
        conn.instruments = resolver
        rest_depth = MarketDepth(
            bids=[DepthLevel(Decimal("1330"), 50, 2)],
            asks=[DepthLevel(Decimal("1331"), 30, 1)],
            depth_type="DEPTH_5",
        )
        conn.market_data.get_depth.return_value = rest_depth

        gw = BrokerGateway.__new__(BrokerGateway)
        gw._conn = conn
        return gw

    def test_none_ws_depth_returns_rest(self):
        gw = self._make_gateway()
        result = gw._complete_depth_snapshot(None, "RELIANCE", "NSE")
        assert result.depth_type == "DEPTH_5"
        assert len(result.bids) == 1
        gw._conn.market_data.get_depth.assert_called_once()

    def test_ws_depth_both_sides_no_rest_call(self):
        gw = self._make_gateway()
        ws = MarketDepth(
            bids=[DepthLevel(Decimal("1330"), 50, 2)],
            asks=[DepthLevel(Decimal("1331"), 30, 1)],
            depth_type="DEPTH_20",
        )
        result = gw._complete_depth_snapshot(ws, "RELIANCE", "NSE")
        assert result.depth_type == "DEPTH_20"
        gw._conn.market_data.get_depth.assert_not_called()

    def test_ws_depth_bids_only_merges_rest_asks(self):
        """When WS has bids but no asks, REST asks are merged in."""
        gw = self._make_gateway()
        ws = MarketDepth(
            bids=[DepthLevel(Decimal("1330"), 50, 2)],
            asks=[],
            depth_type="DEPTH_20",
        )
        result = gw._complete_depth_snapshot(ws, "RELIANCE", "NSE")
        assert result.depth_type == "DEPTH_20"
        assert len(result.bids) == 1
        assert len(result.asks) == 1, "REST asks must be merged when WS asks empty"
        gw._conn.market_data.get_depth.assert_called_once()

    def test_ws_depth_asks_only_merges_rest_bids(self):
        """When WS has asks but no bids, REST bids are merged in."""
        gw = self._make_gateway()
        ws = MarketDepth(
            bids=[],
            asks=[DepthLevel(Decimal("1331"), 30, 1)],
            depth_type="DEPTH_20",
        )
        result = gw._complete_depth_snapshot(ws, "RELIANCE", "NSE")
        assert result.depth_type == "DEPTH_20"
        assert len(result.asks) == 1
        assert len(result.bids) == 1, "REST bids must be merged when WS bids empty"


# ---------------------------------------------------------------------------
# Fix 2 — _send_subscription uses _ws_loop
# ---------------------------------------------------------------------------

class TestSendSubscriptionUsesWsLoop:
    """_send_subscription uses self._ws_loop (not asyncio.get_running_loop)."""

    def _make_feed(self):
        from brokers.dhan.depth_20 import DhanDepth20Feed

        return DhanDepth20Feed("client", "token")

    def test_none_ws_loop_drops_and_increments_counter(self):
        feed = self._make_feed()
        feed._ws = mock.MagicMock()
        feed._ws_loop = None
        assert feed._dropped_depths == 0
        feed._send_subscription([("NSE_EQ", "500325")])
        assert feed._dropped_depths == 1, "Must count drop when _ws_loop is None"

    def test_non_running_loop_drops(self):
        import asyncio
        feed = self._make_feed()
        feed._ws = mock.MagicMock()
        loop = asyncio.new_event_loop()
        # loop exists but is NOT running
        feed._ws_loop = loop
        assert feed._dropped_depths == 0
        feed._send_subscription([("NSE_EQ", "500325")])
        assert feed._dropped_depths == 1, "Must count drop when loop not running"
        loop.close()

    def test_empty_side_does_not_wipe_existing_cache(self):
        """An empty-level packet must not zero out the opposite side."""
        from brokers.dhan.tests.unit.test_depth_feeds import _make_depth_packet

        feed = self._make_feed()
        # Inject bid levels
        bid_packet = _make_depth_packet(41, 500325, [(24500.0, 50, 2)])
        feed._process_binary_message(bid_packet)
        assert feed._depth_cache[500325]["bids"], "bids should be cached"

        # Inject empty ask packet (all qty=0 → filtered out → levels=[])
        ask_packet = _make_depth_packet(51, 500325, [])  # empty
        feed._process_binary_message(ask_packet)

        # bids must still be intact
        with feed._depth_cache_lock:
            bids = feed._depth_cache[500325]["bids"]
        assert bids, "Bids must not be wiped by empty ask packet"


# ---------------------------------------------------------------------------
# Fix 3 — Rate-limit bucket map: read→market_data, write→orders, admin→admin
# ---------------------------------------------------------------------------

class TestRateLimitBucketMap:
    """_rate_limit_bucket maps CB category to MultiBucketRateLimiter name."""

    def test_read_maps_to_market_data(self):
        assert _rate_limit_bucket("/marketfeed/ltp") == "market_data"
        assert _rate_limit_bucket("/marketfeed/quote") == "market_data"
        assert _rate_limit_bucket("/optionchain") == "market_data"
        assert _rate_limit_bucket("/charts/historical") == "market_data"

    def test_write_maps_to_orders(self):
        assert _rate_limit_bucket("/orders") == "orders"
        assert _rate_limit_bucket("/killswitch") == "orders"

    def test_admin_maps_to_admin(self):
        assert _rate_limit_bucket("/fundlimit") == "admin"
        assert _rate_limit_bucket("/positions") == "admin"
        assert _rate_limit_bucket("/holdings") == "admin"

    def test_rl_bucket_map_complete(self):
        """All CB categories have an entry in _RL_BUCKET_MAP."""
        for category in ("read", "write", "admin"):
            assert category in _RL_BUCKET_MAP, f"Missing bucket map entry: {category}"

    def test_acquire_does_not_raise_for_known_endpoints(self):
        """_acquire_rate_limit_token must not raise ValueError for standard endpoints."""
        from brokers.common.resilience.rate_limiter import MultiBucketRateLimiter, RateLimitConfig
        from brokers.dhan.http_client import DhanHttpClient

        limiter = MultiBucketRateLimiter(
            {
                "market_data": RateLimitConfig(rate_per_second=10.0, capacity=10),
                "orders": RateLimitConfig(rate_per_second=25.0, capacity=25),
                "admin": RateLimitConfig(rate_per_second=20.0, capacity=20),
            }
        )
        client = DhanHttpClient(
            client_id="c",
            access_token="t",
            _rate_limiter=limiter,
        )
        # Must not raise — previously this returned True via ValueError bypass
        assert client._acquire_rate_limit_token("/marketfeed/quote") is True
        assert client._acquire_rate_limit_token("/orders") is True
        assert client._acquire_rate_limit_token("/fundlimit") is True


# ---------------------------------------------------------------------------
# Fix 4 — SDK depth list normalisation
# ---------------------------------------------------------------------------

class TestNormalizeSdkDepth:
    """DhanMarketFeed._normalize_sdk_depth handles both SDK shapes."""

    def _feed(self):
        return DhanMarketFeed(client_id="c", access_token="t", instruments=[])

    def test_dict_shape_passthrough(self):
        feed = self._feed()
        raw = {"bids": [{"price": "100", "quantity": 10, "orders": 2}], "asks": []}
        result = feed._normalize_sdk_depth(raw)
        assert result["bids"] == raw["bids"]
        assert result["asks"] == []

    def test_list_shape_converted_to_bids_asks(self):
        """SDK list with bid_price/ask_price per row → {bids, asks}."""
        feed = self._feed()
        raw = [
            {"bid_quantity": 100, "ask_quantity": 50,
             "bid_price": "2450.00", "ask_price": "2451.00",
             "bid_orders": 3, "ask_orders": 2},
        ]
        result = feed._normalize_sdk_depth(raw)
        assert len(result["bids"]) == 1
        assert len(result["asks"]) == 1
        assert result["bids"][0]["price"] == "2450.00"
        assert result["asks"][0]["price"] == "2451.00"

    def test_list_zero_qty_rows_filtered(self):
        """Rows with quantity=0 are not included in bids or asks."""
        feed = self._feed()
        raw = [{"bid_quantity": 0, "ask_quantity": 0,
                "bid_price": "2450.00", "ask_price": "2451.00"}]
        result = feed._normalize_sdk_depth(raw)
        assert result["bids"] == []
        assert result["asks"] == []

    def test_none_returns_empty(self):
        feed = self._feed()
        result = feed._normalize_sdk_depth(None)
        assert result == {"bids": [], "asks": []}

    def test_transform_depth_uses_normalize(self):
        """_transform_depth must use normalised depth, not raw list."""
        feed = self._feed()
        raw = {
            "type": "Market Depth",
            "security_id": 2885,
            "LTP": "2450.50",
            "depth": [
                {"bid_quantity": 100, "ask_quantity": 50,
                 "bid_price": "2450.00", "ask_price": "2451.00"},
            ],
        }
        result = feed._transform_depth(raw)
        depth = result["depth"]
        assert isinstance(depth, dict), "_transform_depth must return dict, not list"
        assert "bids" in depth
        assert "asks" in depth


# ---------------------------------------------------------------------------
# Fix 5 — Bridge DEPTH_20: symbol fallback + Decimal serialisation
# ---------------------------------------------------------------------------

class TestBridgeDepth20:
    """MarketBridge._format_message handles DEPTH_20 events correctly."""

    def _make_bridge(self):
        from api.ws.bridge import MarketBridge
        bus = mock.MagicMock()
        mgr = mock.MagicMock()
        return MarketBridge(bus, mgr)

    def test_depth_20_type_normalised_to_depth(self):
        """DEPTH_20 event must produce type='depth' in the output message."""
        from infrastructure.event_bus import DomainEvent
        bridge = self._make_bridge()
        depth = MarketDepth(
            symbol="RELIANCE",
            bids=[DepthLevel(Decimal("1330"), 50, 2)],
            asks=[DepthLevel(Decimal("1331"), 30, 1)],
            depth_type="DEPTH_20",
        )
        event = DomainEvent.now(
            "DEPTH_20",
            {"depth": depth, "depth_type": "DEPTH_20"},
            symbol="RELIANCE",
            source="test",
        )
        msg = bridge._format_message(event)
        assert msg["type"] == "depth", "DEPTH_20 must be normalised to 'depth'"
        assert msg["symbol"] == "RELIANCE"
        assert isinstance(msg["bids"], list)
        assert isinstance(msg["asks"], list)

    def test_depth_20_symbol_from_payload_when_event_symbol_none(self):
        """When event.symbol is None, symbol is extracted from depth.symbol."""
        from infrastructure.event_bus import DomainEvent
        bridge = self._make_bridge()
        depth = MarketDepth(
            symbol="TCS",
            bids=[DepthLevel(Decimal("2080"), 50, 2)],
            asks=[DepthLevel(Decimal("2081"), 30, 1)],
            depth_type="DEPTH_20",
        )
        # Simulate the pre-fix bug: event published without symbol
        event = DomainEvent.now(
            "DEPTH_20",
            {"depth": depth, "depth_type": "DEPTH_20"},
            symbol=None,
            source="test",
        )
        msg = bridge._format_message(event)
        assert msg["symbol"] == "TCS", "Must fall back to depth.symbol"

    def test_depth_levels_are_json_serialisable(self):
        """Decimal prices must be converted before reaching send_json."""
        import json

        from infrastructure.event_bus import DomainEvent
        bridge = self._make_bridge()
        depth = MarketDepth(
            symbol="RELIANCE",
            bids=[DepthLevel(Decimal("1330.55"), 50, 2)],
            asks=[DepthLevel(Decimal("1331.10"), 30, 1)],
            depth_type="DEPTH_20",
        )
        event = DomainEvent.now(
            "DEPTH_20",
            {"depth": depth},
            symbol="RELIANCE",
            source="test",
        )
        msg = bridge._format_message(event)
        # Must not raise — Decimal would cause TypeError in json.dumps
        serialised = json.dumps(msg)
        assert '"1330.55"' in serialised or "1330.55" in serialised


# ---------------------------------------------------------------------------
# Fix 6 — Quote endpoint interval is 1.0 s
# ---------------------------------------------------------------------------

class TestQuoteRateLimit:
    """/marketfeed/quote must use 1.0 s minimum interval (Dhan documented limit)."""

    def test_quote_interval_is_one_second(self):
        assert _RATE_LIMITS["/marketfeed/quote"] == 1.0, (
            "/marketfeed/quote interval must be 1.0 s (Dhan 1 req/s limit)"
        )

    def test_ltp_interval_faster_than_quote(self):
        assert _RATE_LIMITS["/marketfeed/ltp"] < _RATE_LIMITS["/marketfeed/quote"], (
            "LTP interval must be shorter than quote interval"
        )


# ---------------------------------------------------------------------------
# Audit Fixes — Memory/Callback Leaks and Multiplexing refcount
# ---------------------------------------------------------------------------



class TestAuditLeakAndMultiplexingFixes:
    """Audit verification tests for Dhan connection and WebSocket leak fixes."""

    def test_dhan_connection_token_receiver_weakref(self):
        """DhanConnection uses weak references and avoids leaking stopped feeds."""
        import gc

        from brokers.dhan.connection import DhanConnection
        from brokers.dhan.websocket.market_feed import DhanMarketFeed

        conn = DhanConnection(client=mock.MagicMock())

        # Create a mock feed
        feed = mock.MagicMock(spec=DhanMarketFeed)
        # Register a bound method (update_token)
        conn.register_token_receiver(feed.update_token)

        # Verify it is registered
        assert len(conn._token_manager._token_receivers) == 1

        # Simulate GC of the feed (since the connection only holds a WeakMethod)
        del feed
        gc.collect()

        # Attempt to broadcast — should clean up the dead reference
        notified = conn.broadcast_token("new_token_123")
        assert notified == 0
        assert len(conn._token_manager._token_receivers) == 0

    def test_broker_gateway_callback_leak_prevention(self):
        """BrokerGateway unstream removes wrapper callback from feed."""
        from brokers.dhan.gateway import BrokerGateway
        from brokers.dhan.subscription_engine import SubscriptionEngine

        feed = mock.MagicMock()
        feed.is_connected = False
        conn = mock.MagicMock()
        conn.market_feed = feed
        conn.access_token = "TOKEN"
        conn.create_market_feed = mock.MagicMock(return_value=feed)
        conn.instruments.resolve.return_value = mock.MagicMock(
            security_id="500325", exchange=mock.MagicMock(value="NSE")
        )
        conn.subscription_engine = SubscriptionEngine(conn)

        gw = BrokerGateway(conn)

        cb1 = mock.MagicMock()
        gw.stream("RELIANCE", "NSE", on_tick=cb1)
        assert len(feed.on_quote.call_args_list) == 1
        registered_wrap = feed.on_quote.call_args[0][0]

        gw.unstream("RELIANCE", "NSE", on_tick=cb1)
        feed.off_quote.assert_called_once_with(registered_wrap)
        assert "RELIANCE:NSE" not in conn.subscription_engine._market_callbacks

    def test_market_data_gateway_adapter_ref_counting(self):
        """MarketDataGatewayAdapter tracks active handles and prevents premature stop."""
        import asyncio

        from brokers.common.adapters.market_data_gateway_adapter import wrap_market_gateway
        from brokers.common.broker_port import BrokerStreamPlan

        legacy_gw = mock.MagicMock()
        adapter = wrap_market_gateway(legacy_gw, "dhan")

        plan1 = BrokerStreamPlan(frozenset(["RELIANCE:NSE"]), frozenset(["LTP"]), on_raw_frame=mock.MagicMock())
        plan2 = BrokerStreamPlan(frozenset(["SBIN:NSE"]), frozenset(["LTP"]), on_raw_frame=mock.MagicMock())

        loop = asyncio.new_event_loop()
        try:
            async def run_test():
                # Open two sessions
                h1 = await adapter.open_market_stream(plan1)
                h2 = await adapter.open_market_stream(plan2)

                assert len(adapter._active_market_handles) == 2

                # Disconnect session 1
                await h1.disconnect()

                # Sibling connection should still be open
                legacy_gw.unstream.assert_called_once_with("RELIANCE", "NSE", mock.ANY)
                # Physical feed should NOT have disconnect called
                disconnect = getattr(h1._feed, "disconnect", None)
                if disconnect:
                    disconnect.assert_not_called()

                assert len(adapter._active_market_handles) == 1

                # Disconnect session 2
                await h2.disconnect()
                assert len(adapter._active_market_handles) == 0

            loop.run_until_complete(run_test())
        finally:
            loop.close()
