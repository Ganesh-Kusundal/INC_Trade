"""Dhan portfolio provider — holdings, positions, funds, margin."""

from __future__ import annotations

from typing import Any, Optional

import httpx  # noqa: F401 — needed for test patching

from tradex.broker.auth import AuthManager
from tradex.broker.provider import PortfolioProvider
from tradex.core.errors import BrokerError
from tradex.core.logging_config import get_logger
from tradex.core.metrics import MetricsCollector
from tradex.core.rate_limiter import RateLimiter
from tradex.domain.account import FundLimits
from tradex.domain.enums import ProductType, Side
from tradex.domain.mapping import InstrumentMapper
from tradex.domain.portfolio import Holding, Position
from tradex.providers.dhan.config import DhanConfig
from tradex.providers.dhan.http_client import DhanHTTPClient

logger = get_logger("providers.dhan.portfolio")


class DhanPortfolioProvider(PortfolioProvider):
    """Dhan-specific portfolio provider."""

    def __init__(
        self,
        config: DhanConfig,
        auth_manager: AuthManager,
        http_client: Optional[DhanHTTPClient] = None,
        rate_limiter: Optional[RateLimiter] = None,
        mapper: Optional[InstrumentMapper] = None,
        metrics: Optional[MetricsCollector] = None,
    ) -> None:
        self._config = config
        self._auth = auth_manager
        self._http_client = http_client or DhanHTTPClient(config, auth_manager)
        self._rate_limiter = rate_limiter
        self._mapper = mapper
        self._metrics = metrics

    async def get_holdings(self) -> list[Holding]:
        """Get portfolio holdings."""
        if self._rate_limiter:
            await self._rate_limiter.acquire()

        try:
            data = await self._http_client.get("/v2/holdings")
            holdings = data.get("data", [])
            if isinstance(holdings, list):
                return [Holding.from_dhan(h) for h in holdings]
        except BrokerError:
            logger.warning("holdings_fetch_failed")
        return []

    async def get_positions(self) -> list[Position]:
        """Get current positions."""
        if self._rate_limiter:
            await self._rate_limiter.acquire()

        try:
            data = await self._http_client.get("/v2/positions")
            positions = data.get("data", [])
            if isinstance(positions, list):
                return [Position.from_dhan(p) for p in positions]
        except BrokerError:
            logger.warning("positions_fetch_failed")
        return []

    async def get_fund_limits(self) -> FundLimits:
        """Get fund limits."""
        if self._rate_limiter:
            await self._rate_limiter.acquire()

        try:
            data = await self._http_client.get("/v2/funds")
            return FundLimits.from_dhan(data.get("data", {}))
        except BrokerError:
            logger.warning("fund_limits_fetch_failed")
        return FundLimits()

    async def calculate_margin(
        self,
        security_id: str,
        exchange: str,
        side: Side,
        quantity: int,
        product_type: ProductType,
        price: float,
        trigger_price: float = 0,
    ) -> dict[str, Any]:
        """Calculate margin for a potential order."""
        if self._rate_limiter:
            await self._rate_limiter.acquire()

        payload = {
            "securityId": security_id,
            "exchangeSegment": exchange,
            "transactionType": side.value,
            "quantity": quantity,
            "productType": product_type.value,
            "price": str(price),
            "triggerPrice": str(trigger_price),
        }

        try:
            data = await self._http_client.post("/v2/margincalculator", json=payload)
            margin_data = data.get("data", {})
            return {
                "total_margin": float(margin_data.get("totalMargin", 0)),
                "span_margin": float(margin_data.get("spanMargin", 0)),
                "exposure_margin": float(margin_data.get("exposureMargin", 0)),
                "available_balance": float(margin_data.get("availableBalance", 0)),
                "brokerage": float(margin_data.get("brokerage", 0)),
                "leverage": float(margin_data.get("leverage", 0)),
                "sufficient": float(margin_data.get("availableBalance", 0))
                >= float(margin_data.get("totalMargin", 0)),
                "raw": margin_data,
            }
        except BrokerError:
            logger.warning("margin_calc_failed", security_id=security_id)
        return {}

    # ------------------------------------------------------------------
    # eDIS (e-Delivery Instruction Slip)
    # ------------------------------------------------------------------

    async def generate_tpin(self) -> dict[str, Any]:
        """Generate TPIN for eDIS authorization.

        The TPIN is required before selling delivery holdings.
        After generating, the user must authorize via the CDSL portal.

        Returns:
            Response data containing the TPIN.
        """
        if self._rate_limiter:
            await self._rate_limiter.acquire()

        try:
            data = await self._http_client.post("/v2/edis/tpin")
            logger.info("tpin_generated")
            return data.get("data", {})
        except BrokerError:
            logger.error("tpin_generation_failed")
            raise

    async def edis_inquiry(self, isin: str) -> dict[str, Any]:
        """Check eDIS authorization status for an ISIN.

        Args:
            isin: The ISIN of the security to check. Pass "ALL" for a broad check.

        Returns:
            Response data with approval status fields:
            clientId, isin, totalQty, aprvdQty, status, remarks.
        """
        if self._rate_limiter:
            await self._rate_limiter.acquire()

        try:
            data = await self._http_client.get(f"/v2/edis/inquiry/{isin}")
            return data.get("data", {})
        except BrokerError:
            logger.error("edis_inquiry_failed", isin=isin)
            raise

    # ------------------------------------------------------------------
    # Position Conversion
    # ------------------------------------------------------------------

    async def convert_position(
        self,
        from_product_type: str,
        exchange_segment: str,
        position_type: str,
        security_id: str,
        convert_qty: int,
        to_product_type: str,
    ) -> dict[str, Any]:
        """Convert a position between product types.

        For example, convert an INTRADAY position to CNC (delivery)
        or vice versa.

        Args:
            from_product_type: Current product type (e.g. INTRADAY).
            exchange_segment: Exchange segment (e.g. NSE_EQ).
            position_type: Position direction (LONG, SHORT).
            security_id: The security ID of the position.
            convert_qty: Quantity to convert.
            to_product_type: Target product type (e.g. CNC).

        Returns:
            Response data from the conversion.
        """
        if self._rate_limiter:
            await self._rate_limiter.acquire()

        payload = {
            "fromProductType": from_product_type,
            "exchangeSegment": exchange_segment,
            "positionType": position_type,
            "securityId": security_id,
            "convertQty": convert_qty,
            "toProductType": to_product_type,
        }

        try:
            data = await self._http_client.post("/v2/positions/convert", json=payload)
            logger.info(
                "position_converted",
                security_id=security_id,
                from_type=from_product_type,
                to_type=to_product_type,
            )
            return data.get("data", {})
        except BrokerError:
            logger.error(
                "position_conversion_failed",
                security_id=security_id,
            )
            raise
