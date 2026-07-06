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

# Analytics and context remain in inc_trade for now
# from brokers_core.domain.entities import AggregatedExposure as AggregatedExposure
# from brokers_core.market.analytics import (
#     ATRCalculator as ATRCalculator,
# )
# from brokers_core.market.analytics import (
#     GreeksCalculator as GreeksCalculator,
# )
# from brokers_core.market.analytics import (
#     VolumeProfile as VolumeProfile,
# )
# from brokers_core.market.analytics import (
#     VWAPCalculator as VWAPCalculator,
# )
# from brokers_core.market.config import (
#     MarketDataConfig as MarketDataConfig,
# )
# from brokers_core.market.context import (
#     InstrumentHandle as InstrumentHandle,
# )
# from brokers_core.market.context import MarketDataContext as MarketDataContext
# Scanner imports remain in inc_trade for now
# from inc_trade.market.scanner import (
#     CrossingMA as CrossingMA,
# )
# from inc_trade.market.scanner import (
#     PriceAbove as PriceAbove,
# )
# from inc_trade.market.scanner import (
#     PriceBelow as PriceBelow,
# )
# from inc_trade.market.scanner import (
#     ScanCriteria as ScanCriteria,
# )
# from inc_trade.market.scanner import (
#     Scanner as Scanner,
# )
# from inc_trade.market.scanner import (
#     ScanResult as ScanResult,
# )
# from inc_trade.market.scanner import (
#     VolumeSpike as VolumeSpike,
# )

from brokers_core.market.depth_state import DepthLevelState as DepthLevelState
from brokers_core.market.depth_state import DepthState as DepthState
from brokers_core.market.instrument import Instrument as Instrument
from brokers_core.market.instrument_registry import (
    InstrumentRegistry as InstrumentRegistry,
)
from brokers_core.market.quote_state import QuoteState as QuoteState

__all__ = [
    "DepthLevelState",
    "DepthState",
    "Instrument",
    "InstrumentRegistry",
    "QuoteState",
]
