"""Simulated market data for paper trading."""

from __future__ import annotations

import random
from datetime import datetime, timezone
from decimal import Decimal

from domain import DepthLevel, MarketDepth, Quote


class PaperMarketData:
    """Returns simulated quotes and market depth with realistic random prices."""

    def __init__(self) -> None:
        self._base_prices: dict[str, float] = {}

    def _base(self, symbol: str) -> float:
        if symbol not in self._base_prices:
            self._base_prices[symbol] = 500.0 + random.uniform(0, 4500)
        return self._base_prices[symbol]

    def get_quote(self, symbol: str, exchange: str = "NSE") -> Quote:
        base = self._base(symbol)
        change_pct = random.uniform(-0.02, 0.02)
        ltp_f = base * (1 + change_pct)
        open_f = base
        high_f = max(ltp_f, open_f) * (1 + random.uniform(0, 0.005))
        low_f = min(ltp_f, open_f) * (1 - random.uniform(0, 0.005))
        close_f = base * (1 + random.uniform(-0.01, 0.01))
        volume = random.randint(50_000, 500_000)

        ltp = Decimal(f"{ltp_f:.2f}")
        open_ = Decimal(f"{open_f:.2f}")
        high = Decimal(f"{high_f:.2f}")
        low = Decimal(f"{low_f:.2f}")
        close = Decimal(f"{close_f:.2f}")
        change = ltp - close

        return Quote(
            symbol=symbol,
            ltp=ltp,
            open=open_,
            high=high,
            low=low,
            close=close,
            volume=volume,
            change=change,
            bid=Decimal(f"{ltp_f - 0.50:.2f}"),
            ask=Decimal(f"{ltp_f + 0.50:.2f}"),
            timestamp=datetime.now(timezone.utc),
        )

    def get_ltp(self, symbol: str, exchange: str = "NSE") -> Decimal:
        return self.get_quote(symbol, exchange).ltp

    def get_depth(self, symbol: str, exchange: str = "NSE") -> MarketDepth:
        base = self._base(symbol)
        ltp = base * (1 + random.uniform(-0.01, 0.01))
        bids = [
            DepthLevel(
                price=Decimal(f"{ltp - (i + 1) * 0.50:.2f}"),
                quantity=random.randint(50, 500),
                orders=random.randint(1, 10),
            )
            for i in range(5)
        ]
        asks = [
            DepthLevel(
                price=Decimal(f"{ltp + (i + 1) * 0.50:.2f}"),
                quantity=random.randint(50, 500),
                orders=random.randint(1, 10),
            )
            for i in range(5)
        ]
        return MarketDepth(bids=bids, asks=asks)
