"""Market data capability group for Upstox."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class MarketDataCapability:
    """Quote, historical, options, and futures market data."""

    market_data: Any
    market_data_v2: Any
    market_data_v3: Any
    historical_v2: Any
    historical_v3: Any
    options: Any
    futures: Any
    expired_instruments_client: Any
    market_status: Any
    intelligence: Any
    intelligence_snapshot: Any

    def quote(self, *args: Any, **kwargs: Any) -> Any:
        return self.market_data.get_quote(*args, **kwargs)

    def history(self, *args: Any, **kwargs: Any) -> Any:
        return self.market_data.get_historical(*args, **kwargs)

    def option_chain(self, *args: Any, **kwargs: Any) -> Any:
        return self.options.get_option_chain(*args, **kwargs)
