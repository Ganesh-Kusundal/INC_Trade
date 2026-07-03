"""Dhan capabilities definition — honest BrokerCapabilities matrix."""

from __future__ import annotations

from brokers.domain.capabilities import (
    BrokerCapabilities,
    HistoricalWindowConstraint,
    RateLimitProfile,
    StreamLimitProfile,
)
from brokers.domain.enums import BrokerID


def dhan_capabilities() -> BrokerCapabilities:
    """Authoritative capability snapshot for the Dhan broker adapter."""
    return BrokerCapabilities(
        broker_id=BrokerID.DHAN,
        supports_place_order=True,
        supports_cancel_order=True,
        supports_modify_order=True,
        supports_historical_data=True,
        supports_intraday_history=True,
        supports_expired_options_history=True,
        supports_live_market_data=True,
        supports_depth=True,
        supports_depth_20_ws=True,
        supports_depth_200_ws=True,
        supports_option_chain=True,
        supports_polling_fallback=True,
        supports_order_stream=True,
        supports_portfolio_stream=False,
        supports_news=False,
        supports_fundamentals=False,
        supports_super_order=True,
        supports_forever_order=True,
        supports_native_slice_order=True,
        rate_limit_profiles=(
            RateLimitProfile("orders", 25.0, 50.0, 40, 130),
            RateLimitProfile("quotes", 6.0, 12.0, 167, 130),
            RateLimitProfile("historical", 6.0, 12.0, 167, 130),
            RateLimitProfile("option_chain", 3.0, 6.0, 350, 130),
            RateLimitProfile("funds", 10.0, 20.0, 100, 60),
            RateLimitProfile("positions", 10.0, 20.0, 100, 60),
        ),
        historical_windows=(
            HistoricalWindowConstraint("1m", 3650, 90, True),
            HistoricalWindowConstraint("5m", 3650, 90, True),
            HistoricalWindowConstraint("15m", 3650, 90, True),
            HistoricalWindowConstraint("25m", 3650, 90),
            HistoricalWindowConstraint("60m", 3650, 90),
            HistoricalWindowConstraint("1D", 3650, 365),
        ),
        stream_limits=StreamLimitProfile(
            max_connections=1,
            max_instruments_per_connection=1000,
            max_depth_levels=200,
            supported_stream_modes=frozenset({"LTP", "QUOTE", "FULL", "DEPTH_20", "DEPTH_200"}),
        ),
        latency_class="low",
        reliability_class="tier1",
        product_types=frozenset({"INTRADAY", "MARGIN", "CNC", "MTF"}),
        order_types=frozenset({"MARKET", "LIMIT", "STOP_LOSS", "STOP_LOSS_MARKET"}),
        max_batch_size=1000,
    )
