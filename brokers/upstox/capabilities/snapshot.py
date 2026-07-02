from __future__ import annotations

from brokers.common.capabilities import (
    BrokerCapabilities,
    HistoricalWindowConstraint,
    RateLimitProfile,
    StreamLimitProfile,
)


def upstox_capabilities() -> BrokerCapabilities:
    """Authoritative capability snapshot for the Upstox broker."""
    return BrokerCapabilities(
        broker_id="upstox",
        supports_place_order=True,
        supports_cancel_order=True,
        supports_modify_order=True,
        supports_historical_data=True,
        supports_intraday_history=True,
        supports_expired_options_history=False,
        supports_live_market_data=True,
        supports_depth=True,
        supports_depth_20_ws=False,
        supports_depth_200_ws=False,
        supports_option_chain=True,
        supports_polling_fallback=False,
        supports_order_stream=True,
        supports_portfolio_stream=True,
        supports_news=True,
        supports_fundamentals=True,
        supports_super_order=False,
        supports_forever_order=True,
        supports_native_slice_order=False,
        rate_limit_profiles=(
            RateLimitProfile(
                endpoint_class="orders",
                sustained_rps=10.0,
                burst_rps=20.0,
                min_interval_ms=100,
                cooldown_on_429_s=60,
            ),
            RateLimitProfile(
                endpoint_class="quotes",
                sustained_rps=1.0,
                burst_rps=5.0,
                min_interval_ms=1000,
                cooldown_on_429_s=60,
            ),
            RateLimitProfile(
                endpoint_class="historical",
                sustained_rps=5.0,
                burst_rps=10.0,
                min_interval_ms=200,
                cooldown_on_429_s=60,
            ),
            RateLimitProfile(
                endpoint_class="option_chain",
                sustained_rps=5.0,
                burst_rps=10.0,
                min_interval_ms=200,
                cooldown_on_429_s=60,
            ),
            RateLimitProfile(
                endpoint_class="funds",
                sustained_rps=5.0,
                burst_rps=10.0,
                min_interval_ms=200,
                cooldown_on_429_s=60,
            ),
            RateLimitProfile(
                endpoint_class="positions",
                sustained_rps=5.0,
                burst_rps=10.0,
                min_interval_ms=200,
                cooldown_on_429_s=60,
            ),
            RateLimitProfile(
                endpoint_class="holdings",
                sustained_rps=2.0,
                burst_rps=5.0,
                min_interval_ms=500,
                cooldown_on_429_s=60,
            ),
        ),
        historical_windows=(
            HistoricalWindowConstraint(
                timeframe="1m",
                max_lookback_days=30,
                max_chunk_days=30,
            ),
            HistoricalWindowConstraint(
                timeframe="3m",
                max_lookback_days=30,
                max_chunk_days=30,
            ),
            HistoricalWindowConstraint(
                timeframe="5m",
                max_lookback_days=30,
                max_chunk_days=30,
            ),
            HistoricalWindowConstraint(
                timeframe="15m",
                max_lookback_days=30,
                max_chunk_days=30,
            ),
            HistoricalWindowConstraint(
                timeframe="30m",
                max_lookback_days=30,
                max_chunk_days=30,
            ),
            HistoricalWindowConstraint(
                timeframe="60m",
                max_lookback_days=90,
                max_chunk_days=90,
            ),
            HistoricalWindowConstraint(
                timeframe="4H",
                max_lookback_days=90,
                max_chunk_days=90,
            ),
            HistoricalWindowConstraint(
                timeframe="1D",
                max_lookback_days=3650,
                max_chunk_days=365,
            ),
            HistoricalWindowConstraint(
                timeframe="1W",
                max_lookback_days=3650,
                max_chunk_days=365,
            ),
            HistoricalWindowConstraint(
                timeframe="1M",
                max_lookback_days=3650,
                max_chunk_days=730,
            ),
        ),
        stream_limits=StreamLimitProfile(
            max_connections=2,
            max_instruments_per_connection=5000,
            max_depth_levels=None,
            supported_stream_modes=frozenset({"ltpc", "option_greeks", "full", "full_d30"}),
            combined_mode_caps={
                "ltpc": 2000,
                "option_greeks": 2000,
                "full": 1500,
                "full_d30": 1500,
            },
        ),
        latency_class="medium",
        reliability_class="tier1",
        product_types=frozenset({"INTRADAY", "MARGIN", "CNC"}),
        order_types=frozenset({"MARKET", "LIMIT", "STOP_LOSS", "STOP_LOSS_MARKET"}),
        max_batch_size=10,
    )
