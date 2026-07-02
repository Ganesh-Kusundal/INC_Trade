"""Golden tests for BrokerCapabilities snapshots and query API."""

from brokers.dhan.capabilities import dhan_capabilities
from brokers.upstox.capabilities import upstox_capabilities


class TestDhanCapabilities:
    def test_super_order_and_depth_ws(self):
        caps = dhan_capabilities()
        assert caps.supports("super_order")
        assert caps.supports("depth_20_ws")
        assert caps.supports("expired_options_history")
        assert not caps.supports("news")
        assert not caps.supports("fundamentals")

    def test_intraday_lookback_ten_years(self):
        caps = dhan_capabilities()
        window = caps.historical_window_for("1m")
        assert window is not None
        assert window.max_lookback_days == 3650

    def test_orders_rate_limit_profile(self):
        caps = dhan_capabilities()
        profile = caps.limit_for("orders")
        assert profile is not None
        assert profile.sustained_rps == 25.0


class TestUpstoxCapabilities:
    def test_news_and_no_super_order(self):
        caps = upstox_capabilities()
        assert caps.supports("news")
        assert caps.supports("fundamentals")
        assert not caps.supports("super_order")
        assert not caps.supports("depth_20_ws")

    def test_intraday_lookback_thirty_days(self):
        caps = upstox_capabilities()
        window = caps.historical_window_for("1m")
        assert window is not None
        assert window.max_lookback_days == 30

    def test_can_serve_historical_respects_window(self):
        caps = upstox_capabilities()
        assert caps.can_serve_historical("1m", 30)
        assert not caps.can_serve_historical("1m", 31)
