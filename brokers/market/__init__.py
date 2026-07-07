"""Market Data Context — instruments, quotes, depth, option chains, historical data.

This bounded context owns everything related to market data:
- Instrument entity and registry
- Quote/Depth state
- Option chain data
- Historical data access
- Streaming subscriptions
- InstrumentHandle for instrument-centric access

Market Data MUST NOT import from trading.
"""

# Analytics and context modules
# from brokers.domain.entities import AggregatedExposure as AggregatedExposure
# from brokers.market.analytics import (
#     ATRCalculator as ATRCalculator,
# )
# from brokers.market.analytics import (
#     GreeksCalculator as GreeksCalculator,
# )
# from brokers.market.analytics import (
#     VolumeProfile as VolumeProfile,
# )
# from brokers.market.analytics import (
#     VWAPCalculator as VWAPCalculator,
# )
# from brokers.market.config import (
#     MarketDataConfig as MarketDataConfig,
# )
# from brokers.market.context import (
#     InstrumentHandle as InstrumentHandle,
# )
# from brokers.market.context import MarketDataContext as MarketDataContext
# Scanner modules
# from brokers.market.scanner import (
#     CrossingMA as CrossingMA,
# )
# from brokers.market.scanner import (
#     PriceAbove as PriceAbove,
# )
# from brokers.market.scanner import (
#     PriceBelow as PriceBelow,
# )
# from brokers.market.scanner import (
#     ScanCriteria as ScanCriteria,
# )
# from brokers.market.scanner import (
#     Scanner as Scanner,
# )
# from brokers.market.scanner import (
#     ScanResult as ScanResult,
# )
# from brokers.market.scanner import (
#     VolumeSpike as VolumeSpike,
# )

from brokers.market.config import MarketDataConfig as MarketDataConfig
from brokers.market.depth_state import DepthLevelState as DepthLevelState
from brokers.market.depth_state import DepthState as DepthState
from brokers.market.instrument import Instrument as Instrument
from brokers.market.instrument_registry import (
    InstrumentRegistry as InstrumentRegistry,
)
from brokers.market.quote_state import QuoteState as QuoteState

__all__ = [
    "DepthLevelState",
    "DepthState",
    "Instrument",
    "InstrumentRegistry",
    "MarketDataConfig",
    "QuoteState",
]
