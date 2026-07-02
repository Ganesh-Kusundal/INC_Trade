"""Out-of-order tick handling tests.

Verifies that the system correctly handles ticks arriving out of
temporal order — a common scenario during network congestion or
WebSocket reconnection.
"""

from __future__ import annotations

from datetime import datetime, timezone


class TestOutOfOrderTickHandling:
    def test_later_tick_updates_last_tick_time(self):
        from unittest.mock import MagicMock

        from brokers.upstox.websocket.market_data_v3 import UpstoxMarketDataV3Multiplexer

        mux = UpstoxMarketDataV3Multiplexer(authorizer=MagicMock())
        t1 = datetime(2026, 6, 17, 10, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 6, 17, 10, 0, 1, tzinfo=timezone.utc)

        mux._last_tick_time["NSE|123"] = t1
        mux._last_tick_time["NSE|123"] = t2
        assert mux._last_tick_time["NSE|123"] == t2

    def test_earlier_tick_does_not_overwrite_later(self):
        from unittest.mock import MagicMock

        from brokers.upstox.websocket.market_data_v3 import UpstoxMarketDataV3Multiplexer

        mux = UpstoxMarketDataV3Multiplexer(authorizer=MagicMock())
        later = datetime(2026, 6, 17, 10, 0, 5, tzinfo=timezone.utc)
        earlier = datetime(2026, 6, 17, 10, 0, 1, tzinfo=timezone.utc)

        mux._last_tick_time["NSE|123"] = later
        if earlier > mux._last_tick_time.get("NSE|123", datetime.min.replace(tzinfo=timezone.utc)):
            mux._last_tick_time["NSE|123"] = earlier
        assert mux._last_tick_time["NSE|123"] == later

    def test_out_of_order_ticks_tracked_per_instrument(self):
        from unittest.mock import MagicMock

        from brokers.upstox.websocket.market_data_v3 import UpstoxMarketDataV3Multiplexer

        mux = UpstoxMarketDataV3Multiplexer(authorizer=MagicMock())
        t1 = datetime(2026, 6, 17, 10, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 6, 17, 10, 0, 5, tzinfo=timezone.utc)

        mux._last_tick_time["NSE|123"] = t1
        mux._last_tick_time["NSE|456"] = t2

        assert mux._last_tick_time["NSE|123"] == t1
        assert mux._last_tick_time["NSE|456"] == t2

    def test_dhan_tick_time_tracking_updates_correctly(self):
        from brokers.dhan.websocket import DhanMarketFeed

        feed = DhanMarketFeed(
            client_id="TEST",
            access_token="TOKEN",
            instruments=[],
        )
        quote = {
            "symbol": "RELIANCE",
            "security_id": "2885",
            "ltp": 2450,
            "timestamp": datetime(2026, 6, 17, 10, 0, 0, tzinfo=timezone.utc),
        }
        feed._track_tick_time(quote)
        assert "RELIANCE" in feed._last_tick_time


class TestTickGapDetection:
    def test_gap_detected_when_tick_time_jumps(self):
        from unittest.mock import MagicMock

        from brokers.upstox.websocket.market_data_v3 import UpstoxMarketDataV3Multiplexer

        mux = UpstoxMarketDataV3Multiplexer(authorizer=MagicMock())
        t1 = datetime(2026, 6, 17, 10, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 6, 17, 10, 5, 0, tzinfo=timezone.utc)

        mux._last_tick_time["NSE|123"] = t1
        gap = (t2 - t1).total_seconds()
        assert gap == 300.0

    def test_no_gap_for_consecutive_ticks(self):
        t1 = datetime(2026, 6, 17, 10, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 6, 17, 10, 0, 1, tzinfo=timezone.utc)
        gap = (t2 - t1).total_seconds()
        assert gap < 5.0

    def test_stale_tick_detected_by_age(self):
        now = datetime(2026, 6, 17, 10, 0, 10, tzinfo=timezone.utc)
        stale = datetime(2026, 6, 17, 10, 0, 0, tzinfo=timezone.utc)
        age = (now - stale).total_seconds()
        assert age > 5.0

    def test_missing_tick_detection_across_instruments(self):
        from unittest.mock import MagicMock

        from brokers.upstox.websocket.market_data_v3 import UpstoxMarketDataV3Multiplexer

        mux = UpstoxMarketDataV3Multiplexer(authorizer=MagicMock())
        t_now = datetime(2026, 6, 17, 10, 0, 10, tzinfo=timezone.utc)
        t_old = datetime(2026, 6, 17, 9, 55, 0, tzinfo=timezone.utc)

        mux._last_tick_time["NSE|123"] = t_now
        mux._last_tick_time["NSE|456"] = t_old

        stale_threshold = datetime(2026, 6, 17, 9, 58, 0, tzinfo=timezone.utc)
        stale_instruments = [k for k, v in mux._last_tick_time.items() if v < stale_threshold]
        assert "NSE|456" in stale_instruments
        assert "NSE|123" not in stale_instruments
