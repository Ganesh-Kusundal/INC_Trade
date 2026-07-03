"""Broker capability model — runtime feature and limit matrix."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone

from brokers.domain.enums import BrokerID

__all__ = [
    "BrokerCapabilities",
    "CapabilityDescriptor",
    "HistoricalWindowConstraint",
    "RateLimitProfile",
    "StreamLimitProfile",
]


@dataclass(frozen=True)
class RateLimitProfile:
    endpoint_class: str
    sustained_rps: float
    burst_rps: float | None = None
    min_interval_ms: int | None = None
    cooldown_on_429_s: int | None = None


@dataclass(frozen=True)
class HistoricalWindowConstraint:
    timeframe: str
    max_lookback_days: int
    max_chunk_days: int
    supports_expired_instruments: bool = False


@dataclass(frozen=True)
class StreamLimitProfile:
    max_connections: int
    max_instruments_per_connection: int
    max_depth_levels: int | None
    supported_stream_modes: frozenset[str]
    combined_mode_caps: Mapping[str, int] | None = None


@dataclass(frozen=True)
class BrokerCapabilities:
    broker_id: str | BrokerID
    supports_place_order: bool = False
    supports_cancel_order: bool = False
    supports_modify_order: bool = False
    supports_historical_data: bool = False
    supports_intraday_history: bool = False
    supports_expired_options_history: bool = False
    supports_live_market_data: bool = False
    supports_depth: bool = False
    supports_depth_20_ws: bool = False
    supports_depth_200_ws: bool = False
    supports_option_chain: bool = False
    supports_polling_fallback: bool = False
    supports_order_stream: bool = False
    supports_portfolio_stream: bool = False
    supports_news: bool = False
    supports_fundamentals: bool = False
    supports_super_order: bool = False
    supports_forever_order: bool = False
    supports_native_slice_order: bool = False
    rate_limit_profiles: tuple[RateLimitProfile, ...] = field(default_factory=tuple)
    historical_windows: tuple[HistoricalWindowConstraint, ...] = field(default_factory=tuple)
    stream_limits: StreamLimitProfile | None = None
    latency_class: str = "medium"
    reliability_class: str = "tier2"
    product_types: frozenset[str] = field(default_factory=frozenset)
    order_types: frozenset[str] = field(default_factory=frozenset)
    max_batch_size: int = 1

    def supports(self, feature: str) -> bool:
        return bool(getattr(self, f"supports_{feature}", False))

    def limit_for(self, endpoint_class: str) -> RateLimitProfile | None:
        for profile in self.rate_limit_profiles:
            if profile.endpoint_class == endpoint_class:
                return profile
        return None

    def historical_window_for(self, timeframe: str) -> HistoricalWindowConstraint | None:
        for constraint in self.historical_windows:
            if constraint.timeframe == timeframe:
                return constraint
        return None

    def can_serve_historical(self, timeframe: str, lookback_days: int) -> bool:
        if not self.supports_historical_data:
            return False
        constraint = self.historical_window_for(timeframe)
        if constraint is None:
            return False
        return lookback_days <= constraint.max_lookback_days


@dataclass(frozen=True)
class CapabilityDescriptor:
    broker_id: str | BrokerID
    capabilities: BrokerCapabilities
    extensions: frozenset[str]
    observed_at: datetime

    @classmethod
    def build(
        cls,
        capabilities: BrokerCapabilities,
        extensions: frozenset[str],
    ) -> CapabilityDescriptor:
        return cls(
            broker_id=capabilities.broker_id,
            capabilities=capabilities,
            extensions=extensions,
            observed_at=datetime.now(tz=timezone.utc),
        )
