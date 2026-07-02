"""Upstox market data adapter — implements ``MarketDataProvider`` port.

Mirrors Trade_J ``UpstoxMarketDataProvider``.
Fixed P-2.1: Now implements correct ABC interface (quote, ltp, depth, history).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pandas as pd

from brokers.common.api import MarketDataProvider
from brokers.upstox.mappers.domain_mapper import UpstoxDomainMapper
from brokers.upstox.market_data.client_v2 import UpstoxMarketDataV2Client
from brokers.upstox.market_data.client_v3 import UpstoxMarketDataV3Client
from brokers.upstox.market_data.historical_v2 import UpstoxHistoricalV2Client
from domain import HistoricalCandle, MarketDepth, OptionContract, Quote


class UpstoxMarketDataAdapter(MarketDataProvider):
    """P-2.1: Fixed ISP violation - now implements correct ABC interface."""

    def __init__(
        self,
        v2: UpstoxMarketDataV2Client,
        v3: UpstoxMarketDataV3Client,
        historical: UpstoxHistoricalV2Client,
    ) -> None:
        self._v2 = v2
        self._v3 = v3
        self._historical = historical

    # P-2.1: Implement correct ABC interface methods

    def quote(self, symbol: str, exchange: str = "NSE") -> Quote:
        """Fetch full quote with OHLCV for an instrument.

        P-2.1: Fixed - renamed from get_quote() to match ABC.
        """
        instrument_key = symbol if "|" in symbol else f"{_segment_wire(exchange)}|{symbol}"
        body = self._v2.get_quote([instrument_key])
        return UpstoxDomainMapper.to_quote(body)

    def ltp(self, symbol: str, exchange: str = "NSE") -> Decimal:
        """Fetch last traded price.

        P-2.1: Fixed - new method required by ABC.
        """
        instrument_key = symbol if "|" in symbol else f"{_segment_wire(exchange)}|{symbol}"
        body = self._v2.get_quote([instrument_key])
        quote = UpstoxDomainMapper.to_quote(body)
        return quote.ltp

    def depth(self, symbol: str, exchange: str = "NSE") -> MarketDepth:
        """Fetch order book depth.

        P-2.1: Fixed - renamed from get_depth() to match ABC.
        """
        instrument_key = symbol if "|" in symbol else f"{_segment_wire(exchange)}|{symbol}"
        body = self._v2.get_order_book(instrument_key)
        return UpstoxDomainMapper.to_market_depth(body)

    def history(
        self,
        symbol: str | list[str],
        exchange: str = "NSE",
        timeframe: str = "1D",
        lookback_days: int = 90,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> pd.DataFrame:
        """Fetch historical candle data.

        P-2.1: Fixed - renamed from get_historical_*() to match ABC.
        Consolidates daily and intraday into single method.
        """
        if isinstance(symbol, list):
            # ABC supports multiple symbols, but Upstox API takes one at a time
            # Take first symbol for now
            symbol = symbol[0]

        instrument_key = symbol if "|" in symbol else f"{_segment_wire(exchange)}|{symbol}"

        # Determine candle interval from timeframe
        interval = timeframe.lower()
        if interval == "1d":
            interval = "day"
        elif interval == "1h":
            interval = "1hour"
        elif interval == "15m":
            interval = "15minute"
        elif interval == "5m":
            interval = "5minute"
        elif interval == "1m":
            interval = "1minute"

        # Parse dates
        from datetime import datetime, timedelta
        to_dt = datetime.now() if to_date is None else datetime.fromisoformat(to_date)

        if from_date is None:
            from_dt = to_dt - timedelta(days=lookback_days)
        else:
            from_dt = datetime.fromisoformat(from_date)

        body = self._historical.get_candles(
            instrument_key, interval, to_dt.date(), from_dt.date()
        )
        candles = UpstoxDomainMapper.to_historical_candles(body)

        # Convert to DataFrame for ABC compliance
        if not candles:
            return pd.DataFrame()

        return pd.DataFrame([
            {
                "timestamp": c.timestamp,
                "open": float(c.open),
                "high": float(c.high),
                "low": float(c.low),
                "close": float(c.close),
                "volume": c.volume,
            }
            for c in candles
        ])

    # Legacy methods retained for backward compatibility (internal use)

    def get_historical_daily(
        self,
        security_id: str,
        exchange_segment: Any,
        from_date: date,
        to_date: date,
        instrument: str = "EQUITY",
    ) -> list[HistoricalCandle]:
        """Legacy method - use history() instead."""
        instrument_key = f"{_segment_wire(exchange_segment)}|{security_id}"
        body = self._historical.get_candles(instrument_key, "day", to_date, from_date)
        return UpstoxDomainMapper.to_historical_candles(body)

    def get_historical_intraday(
        self,
        security_id: str,
        exchange_segment: Any,
        from_date: date,
        to_date: date,
        interval: str | None = None,
    ) -> list[HistoricalCandle]:
        """Legacy method - use history() instead."""
        instrument_key = f"{_segment_wire(exchange_segment)}|{security_id}"
        body = self._historical.get_candles(
            instrument_key, interval or "1minute", to_date, from_date
        )
        return UpstoxDomainMapper.to_historical_candles(body)

    def get_option_chain(
        self, underlying: str, exchange_segment: Any, expiry: str
    ) -> list[OptionContract]:
        """Delegated to UpstoxOptionsAdapter."""
        return []

    def get_option_expiries(self, underlying: str, exchange_segment: Any) -> list[str]:
        """Delegated to UpstoxOptionsAdapter."""
        return []


def _segment_wire(segment: Any) -> str:
    from brokers.upstox.mappers.domain_mapper import UpstoxDomainMapper

    return UpstoxDomainMapper.segment_to_wire(segment)
