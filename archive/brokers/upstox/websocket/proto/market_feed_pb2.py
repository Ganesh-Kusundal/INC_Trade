"""Generated Python stub for Upstox V3 MarketDataFeed.proto.

Re-exports from MarketDataFeed_pb2.
"""

from __future__ import annotations

try:
    from .MarketDataFeed_pb2 import (
        LTPC,
        MarketLevel,
        MarketOHLC,
        Quote,
        OptionGreeks,
        OHLC,
        Type,
        MarketFullFeed,
        IndexFullFeed,
        FullFeed,
        FirstLevelWithGreeks,
        Feed,
        RequestMode,
        MarketStatus,
        MarketInfo,
        FeedResponse,
    )
except ImportError:
    try:
        from MarketDataFeed_pb2 import (
            LTPC,
            MarketLevel,
            MarketOHLC,
            Quote,
            OptionGreeks,
            OHLC,
            Type,
            MarketFullFeed,
            IndexFullFeed,
            FullFeed,
            FirstLevelWithGreeks,
            Feed,
            RequestMode,
            MarketStatus,
            MarketInfo,
            FeedResponse,
        )
    except ImportError:
        # Fallback dummy class if import fails in unit tests
        class FeedResponse:
            pass
        class Feed:
            pass
