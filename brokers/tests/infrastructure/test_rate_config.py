"""Tests for per-endpoint rate limit configuration."""

from __future__ import annotations

import pytest

from brokers.infrastructure.rate_config import (
    RateLimitConfig,
    dhan_rate_config,
    upstox_rate_config,
)


class TestRateLimitConfig:
    def test_get_interval_exact_match(self):
        config = RateLimitConfig(limits={"/marketfeed/quote": 1.0})
        assert config.get_interval("/marketfeed/quote") == 1.0

    def test_get_interval_prefix_match(self):
        config = RateLimitConfig(limits={"/charts/": 0.1})
        assert config.get_interval("/charts/historical") == 0.1

    def test_get_interval_no_match(self):
        config = RateLimitConfig(limits={"/orders": 0.04})
        assert config.get_interval("/unknown/endpoint") == 0.0

    def test_exact_match_takes_priority_over_prefix(self):
        config = RateLimitConfig(limits={"/orders": 0.04, "/orders/": 0.1})
        # Exact match wins
        assert config.get_interval("/orders") == 0.04

    def test_categorize_write(self):
        config = RateLimitConfig(write_prefixes=("/orders",))
        assert config.categorize("/orders") == "write"
        assert config.categorize("/orders/123") == "write"

    def test_categorize_read(self):
        config = RateLimitConfig(read_prefixes=("/marketfeed/",))
        assert config.categorize("/marketfeed/ltp") == "read"

    def test_categorize_admin_default(self):
        config = RateLimitConfig(
            read_prefixes=("/marketfeed/",),
            write_prefixes=("/orders",),
        )
        assert config.categorize("/positions") == "admin"
        assert config.categorize("/unknown") == "admin"

    def test_write_takes_priority_over_read(self):
        config = RateLimitConfig(
            read_prefixes=("/v2/",),
            write_prefixes=("/v2/order/place",),
        )
        assert config.categorize("/v2/order/place") == "write"

    def test_frozen_dataclass(self):
        config = RateLimitConfig()
        with pytest.raises(Exception):
            config.limits = {}  # type: ignore[misc]


class TestDhanRateConfig:
    def test_dhan_config_has_quote_limit(self):
        config = dhan_rate_config()
        assert config.get_interval("/marketfeed/quote") == 1.0

    def test_dhan_config_has_order_limit(self):
        config = dhan_rate_config()
        assert config.get_interval("/orders") == 0.04

    def test_dhan_categorizes_orders_as_write(self):
        config = dhan_rate_config()
        assert config.categorize("/orders") == "write"
        assert config.categorize("/orders/123") == "write"

    def test_dhan_categorizes_market_data_as_read(self):
        config = dhan_rate_config()
        assert config.categorize("/marketfeed/ltp") == "read"
        assert config.categorize("/marketfeed/quote") == "read"
        assert config.categorize("/charts/historical") == "read"

    def test_dhan_categorizes_portfolio_as_admin(self):
        config = dhan_rate_config()
        assert config.categorize("/positions") == "admin"
        assert config.categorize("/holdings") == "admin"
        assert config.categorize("/fundlimit") == "admin"

    def test_dhan_returns_new_instance_each_call(self):
        c1 = dhan_rate_config()
        c2 = dhan_rate_config()
        assert c1 is not c2
        assert c1.limits == c2.limits


class TestUpstoxRateConfig:
    def test_upstox_config_has_order_limit(self):
        config = upstox_rate_config()
        assert config.get_interval("/v2/order/place") == 0.04

    def test_upstox_categorizes_order_place_as_write(self):
        config = upstox_rate_config()
        assert config.categorize("/v2/order/place") == "write"
        assert config.categorize("/v2/order/cancel") == "write"
        assert config.categorize("/v2/order/modify") == "write"

    def test_upstox_categorizes_market_data_as_read(self):
        config = upstox_rate_config()
        assert config.categorize("/v2/market-quote/ltp") == "read"
        assert config.categorize("/v2/historical-candle/intraday") == "read"

    def test_upstox_categorizes_portfolio_as_admin(self):
        config = upstox_rate_config()
        assert config.categorize("/v2/portfolio/short-term-positions") == "admin"

    def test_upstox_historical_candle_rate(self):
        config = upstox_rate_config()
        assert config.get_interval("/v2/historical-candle/daily") == 0.1
