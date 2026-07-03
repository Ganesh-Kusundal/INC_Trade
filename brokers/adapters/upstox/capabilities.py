"""Upstox broker capabilities definition."""

from __future__ import annotations

from brokers.domain.capabilities import (
    BrokerCapabilities,
    HistoricalWindowConstraint,
    RateLimitProfile,
    StreamLimitProfile,
)


def upstox_capabilities() -> BrokerCapabilities:
    """Authoritative capability snapshot for the Upstox broker adapter."""
    return BrokerCapabilities(
        broker_id="upstox",
        supports_place_order=True,
        supports_cancel_order=True,
        supports_modify_order=True,
        supports_historical_data=True,
        supports_intraday_history=True,
        supports_expired_options_history=True,
        supports_live_market_data=True,
        supports_depth=True,
        supports_depth_20_ws=False,  # Upstox supports up to depth 30
        supports_depth_200_ws=False,
        supports_option_chain=True,
        supports_polling_fallback=True,
        supports_order_stream=True,
        supports_portfolio_stream=True,
        supports_news=True,
        supports_fundamentals=False,
        supports_super_order=False,  # Not native to Upstox
        supports_forever_order=True,  # GTT orders
        supports_native_slice_order=False,
        rate_limit_profiles=(
            RateLimitProfile("orders", 20.0, 40.0, 50, 60),
            RateLimitProfile("quotes", 5.0, 10.0, 200, 60),
            RateLimitProfile("historical", 5.0, 10.0, 200, 60),
            RateLimitProfile("option_chain", 2.0, 4.0, 500, 60),
            RateLimitProfile("funds", 8.0, 16.0, 125, 60),
            RateLimitProfile("positions", 8.0, 16.0, 125, 60),
        ),
        historical_windows=(
            HistoricalWindowConstraint("1m", 365, 30, True),  # 1 year max for intraday
            HistoricalWindowConstraint("5m", 365, 90, True),
            HistoricalWindowConstraint("15m", 365, 90, True),
            HistoricalWindowConstraint("30m", 365, 90, True),
            HistoricalWindowConstraint("60m", 365, 90, True),
            HistoricalWindowConstraint("1D", 1800, 365),  # 5 years for daily
        ),
        stream_limits=StreamLimitProfile(
            max_connections=1,
            max_instruments_per_connection=1000,
            max_depth_levels=30,
            supported_stream_modes=frozenset(
                {"LTP", "QUOTE", "FULL", "DEPTH_5", "DEPTH_30"}
            ),
        ),
        latency_class="low",
        reliability_class="tier1",
        product_types=frozenset({"INTRADAY", "DELIVERY", "MARGIN"}),
        order_types=frozenset({"MARKET", "LIMIT", "STOP_LOSS", "STOP_LOSS_MARKET"}),
        max_batch_size=500,
    )
