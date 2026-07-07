"""Dhan market data provider — quotes, history, option chain."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

import httpx  # noqa: F401 — needed for test patching

from tradex.broker.auth import AuthManager
from tradex.broker.provider import MarketDataProvider
from tradex.core.errors import BrokerError
from tradex.core.logging_config import get_logger
from tradex.core.metrics import MetricsCollector
from tradex.core.rate_limiter import RateLimiter
from tradex.domain.market_data import (
    OHLCV,
    DepthLevel,
    MarketDepth,
    OptionChain,
    Quote,
)
from tradex.providers.dhan.config import DhanConfig
from tradex.providers.dhan.http_client import DhanHTTPClient
from tradex.providers.dhan.instruments import DhanInstrumentMapper

logger = get_logger("providers.dhan.market")


class DhanMarketDataProvider(MarketDataProvider):
    """Dhan-specific market data provider."""

    def __init__(
        self,
        config: DhanConfig,
        auth_manager: AuthManager,
        http_client: Optional[DhanHTTPClient] = None,
        rate_limiter: Optional[RateLimiter] = None,
        data_rate_limiter: Optional[RateLimiter] = None,
        mapper: Optional[DhanInstrumentMapper] = None,
        metrics: Optional[MetricsCollector] = None,
    ) -> None:
        self._config = config
        self._auth = auth_manager
        self._http_client = http_client or DhanHTTPClient(config, auth_manager)
        self._rate_limiter = rate_limiter
        self._data_rate_limiter = data_rate_limiter
        self._mapper = mapper
        self._metrics = metrics

    async def get_quote(self, security_id: str, exchange: str) -> Quote:
        """Get a real-time quote snapshot."""
        if self._rate_limiter:
            await self._rate_limiter.acquire()

        securities = {exchange: [int(security_id)]}

        data = await self._http_client.post("/v2/quotes", json=securities)

        quote_data = data.get("data", {})
        if exchange in quote_data:
            instruments = quote_data[exchange]
            q_data = instruments.get(security_id) or instruments.get(str(security_id)) or instruments.get(int(security_id))
            if q_data:
                return Quote.from_dhan_quote(exchange, security_id, q_data)
        return Quote(security_id=security_id, exchange=exchange)

    async def get_quotes(self, securities: dict[str, list[str]]) -> dict[str, dict[str, Quote]]:
        """Get quotes for multiple instruments."""
        if self._rate_limiter:
            await self._rate_limiter.acquire()

        # Convert string IDs to ints for Dhan API
        dhan_securities = {}
        for exchange, ids in securities.items():
            dhan_securities[exchange] = [int(sid) for sid in ids]

        try:
            data = await self._http_client.post("/v2/quotes", json=dhan_securities)

            result: dict[str, dict[str, Quote]] = {}
            quote_data = data.get("data", {})
            for exchange, instruments in quote_data.items():
                result[exchange] = {}
                for sec_id_str, q_data in instruments.items():
                    result[exchange][sec_id_str] = Quote.from_dhan_quote(
                        exchange, sec_id_str, q_data
                    )
            return result
        except BrokerError:
            logger.warning("quotes_fetch_failed")
            return {}

    async def get_ohlcv(
        self,
        security_id: str,
        exchange: str,
        instrument_type: str,
        start_date: str,
        end_date: str,
        expiry_code: int = 0,
        include_oi: bool = False,
    ) -> list[OHLCV]:
        """Get historical daily OHLCV data."""
        if self._data_rate_limiter:
            await self._data_rate_limiter.acquire()

        payload = {
            "securityId": security_id,
            "exchangeSegment": exchange,
            "instrument": instrument_type,
            "expiryCode": expiry_code,
            "FromDate": start_date,
            "ToDate": end_date,
            "oi": include_oi,
        }

        data = await self._http_client.post("/v2/charts", json=payload)

        candles = data.get("data", {})
        if isinstance(candles, dict) and "timestamp" in candles:
            count = len(candles.get("timestamp", []))
            return [OHLCV.from_dict(candles, i) for i in range(count)]
        return []

    async def get_minute_data(
        self,
        security_id: str,
        exchange: str,
        instrument_type: str,
        start_date: str,
        end_date: str,
        interval: int = 1,
        include_oi: bool = False,
    ) -> list[OHLCV]:
        """Get intraday minute data."""
        if self._data_rate_limiter:
            await self._data_rate_limiter.acquire()

        payload = {
            "securityId": security_id,
            "exchangeSegment": exchange,
            "instrument": instrument_type,
            "FromDate": start_date,
            "ToDate": end_date,
            "interval": interval,
            "oi": include_oi,
        }

        try:
            data = await self._http_client.post("/v2/charts/intraday", json=payload)

            candles = data.get("data", {})
            if isinstance(candles, dict) and "timestamp" in candles:
                count = len(candles.get("timestamp", []))
                return [OHLCV.from_dict(candles, i) for i in range(count)]
        except BrokerError:
            logger.warning("minute_data_fetch_failed", security_id=security_id)
        return []

    async def get_option_chain(
        self,
        underlying_security_id: str,
        exchange: str,
        expiry: str,
    ) -> OptionChain:
        """Get option chain for an underlying."""
        if self._rate_limiter:
            await self._rate_limiter.acquire()

        data = await self._http_client.post(
            "/v2/optionchain",
            json={
                "underlyingSecurityId": int(underlying_security_id),
                "underlyingExchangeSegment": exchange,
                "expiry": expiry,
            },
        )
        return OptionChain.from_dhan(data, expiry=expiry)

    async def get_expiry_list(self, underlying_security_id: str, exchange: str) -> list[str]:
        """Get available expiry dates."""
        if self._rate_limiter:
            await self._rate_limiter.acquire()

        try:
            data = await self._http_client.get(
                f"/v2/expirylist/{underlying_security_id}/{exchange}"
            )
            return data.get("data", [])
        except BrokerError:
            logger.warning("expiry_list_fetch_failed", security_id=underlying_security_id)
            return []

    async def get_depth(self, security_id: str, exchange: str) -> MarketDepth:
        """Get market depth snapshot with buy/sell levels."""
        if self._rate_limiter:
            await self._rate_limiter.acquire()

        securities = {exchange: [int(security_id)]}
        data = await self._http_client.post("/v2/quotes", json=securities)

        quote_data = data.get("data", {})

        # Navigate into the exchange / security_id structure
        instrument_data: dict[str, Any] = {}
        if exchange in quote_data:
            exchange_data = quote_data[exchange]
            if isinstance(exchange_data, dict):
                for key, val in exchange_data.items():
                    if str(key) == str(security_id):
                        instrument_data = val if isinstance(val, dict) else {}
                        break

        depth_raw = instrument_data.get("depth", {})
        buy_raw = depth_raw.get("buy", []) if isinstance(depth_raw, dict) else []
        sell_raw = depth_raw.get("sell", []) if isinstance(depth_raw, dict) else []

        # Merge buy and sell into DepthLevel rows
        max_levels = max(len(buy_raw), len(sell_raw))
        levels: list[DepthLevel] = []
        for i in range(max_levels):
            buy_level = buy_raw[i] if i < len(buy_raw) else {}
            sell_level = sell_raw[i] if i < len(sell_raw) else {}

            levels.append(
                DepthLevel(
                    bid_price=Decimal(str(buy_level.get("price", 0))),
                    bid_quantity=int(buy_level.get("quantity", 0)),
                    bid_orders=int(buy_level.get("orders", 0)),
                    ask_price=Decimal(str(sell_level.get("price", 0))),
                    ask_quantity=int(sell_level.get("quantity", 0)),
                    ask_orders=int(sell_level.get("orders", 0)),
                )
            )

        return MarketDepth(
            security_id=security_id,
            exchange=exchange,
            levels=levels,
        )

    # ------------------------------------------------------------------
    # Expired Options Data
    # ------------------------------------------------------------------

    async def get_expired_options_data(
        self,
        security_id: str,
        exchange_segment: str,
        instrument_type: str,
        expiry_flag: str,
        expiry_code: int,
        strike: str,
        option_type: str,
        required_data: list[str],
        start_date: str,
        end_date: str,
        interval: int = 1,
    ) -> dict[str, Any]:
        """Get historical data for expired options contracts.

        Args:
            security_id: Underlying security ID.
            exchange_segment: Exchange segment (e.g. NSE_FNO).
            instrument_type: Instrument type (e.g. OPTIDX).
            expiry_flag: Expiry flag (MONTH, WEEK).
            expiry_code: Expiry code (1, 2, ...).
            strike: Strike specification (ATM, ATM+N, ATM-N).
            option_type: CALL or PUT.
            required_data: List of data fields to fetch.
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).
            interval: Candle interval in minutes.

        Returns:
            Raw response data with OHLCV arrays for the expired option.
        """
        if self._data_rate_limiter:
            await self._data_rate_limiter.acquire()

        payload = {
            "securityId": security_id,
            "exchangeSegment": exchange_segment,
            "instrument": instrument_type,
            "expiryFlag": expiry_flag,
            "expiryCode": expiry_code,
            "strike": strike,
            "drvOptionType": option_type,
            "requiredData": required_data,
            "FromDate": start_date,
            "ToDate": end_date,
            "interval": interval,
        }

        try:
            data = await self._http_client.post("/v2/charts/expired", json=payload)
            return data.get("data", {})
        except BrokerError:
            logger.error("expired_options_data_failed", security_id=security_id)
            raise
