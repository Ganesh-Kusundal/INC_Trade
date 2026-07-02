from __future__ import annotations

from brokers.common.capabilities import (
    BrokerCapabilities,
    HistoricalWindowConstraint,
    RateLimitProfile,
    StreamLimitProfile,
)


def dhan_capabilities() -> BrokerCapabilities:
    """Authoritative capability snapshot for the Dhan broker.
    
    NOTE ON DEPTH_200 LIMITATION:
        Dhan's depth-200 WebSocket API only supports 1 instrument per connection.
        To monitor multiple instruments at 200-level depth, you must create multiple
        connections. Use Depth200ConnectionPool from brokers.dhan.depth_200 for
        efficient connection management.
    """
    return BrokerCapabilities(
        broker_id="dhan",
        supports_place_order=True,
        supports_cancel_order=True,
        supports_modify_order=True,
        supports_historical_data=True,
        supports_intraday_history=True,
        supports_expired_options_history=True,
        supports_live_market_data=True,
        supports_depth=True,
        supports_depth_20_ws=True,
        supports_depth_200_ws=True,  # LIMITATION: 1 instrument per connection
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
            RateLimitProfile(
                endpoint_class="orders",
                sustained_rps=25.0,
                burst_rps=50.0,
                min_interval_ms=40,
                cooldown_on_429_s=130,
            ),
            RateLimitProfile(
                endpoint_class="quotes",
                sustained_rps=6.0,
                burst_rps=12.0,
                min_interval_ms=167,
                cooldown_on_429_s=130,
            ),
            RateLimitProfile(
                endpoint_class="historical",
                sustained_rps=6.0,
                burst_rps=12.0,
                min_interval_ms=167,
                cooldown_on_429_s=130,
            ),
            RateLimitProfile(
                endpoint_class="option_chain",
                sustained_rps=3.0,
                burst_rps=6.0,
                min_interval_ms=350,
                cooldown_on_429_s=130,
            ),
            RateLimitProfile(
                endpoint_class="funds",
                sustained_rps=10.0,
                burst_rps=20.0,
                min_interval_ms=100,
                cooldown_on_429_s=60,
            ),
            RateLimitProfile(
                endpoint_class="positions",
                sustained_rps=10.0,
                burst_rps=20.0,
                min_interval_ms=100,
                cooldown_on_429_s=60,
            ),
        ),
        historical_windows=(
            HistoricalWindowConstraint(
                timeframe="1m",
                max_lookback_days=3650,
                max_chunk_days=90,
                supports_expired_instruments=True,
            ),
            HistoricalWindowConstraint(
                timeframe="5m",
                max_lookback_days=3650,
                max_chunk_days=90,
                supports_expired_instruments=True,
            ),
            HistoricalWindowConstraint(
                timeframe="15m",
                max_lookback_days=3650,
                max_chunk_days=90,
                supports_expired_instruments=True,
            ),
            HistoricalWindowConstraint(
                timeframe="25m",
                max_lookback_days=3650,
                max_chunk_days=90,
            ),
            HistoricalWindowConstraint(
                timeframe="60m",
                max_lookback_days=3650,
                max_chunk_days=90,
            ),
            HistoricalWindowConstraint(
                timeframe="1D",
                max_lookback_days=3650,
                max_chunk_days=365,
            ),
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
