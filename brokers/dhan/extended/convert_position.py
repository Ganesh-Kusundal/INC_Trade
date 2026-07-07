"""Dhan convert position — convert between product types (intraday ↔ delivery).

API: POST /positions/convert
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from brokers.infrastructure.http_client import BaseHttpClient
from brokers.infrastructure.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ConvertPositionRequest:
    """Request to convert a position between product types."""

    security_id: str
    exchange_segment: str
    position_type: str  # LONG or SHORT
    convert_qty: int
    from_product_type: str  # INTRADAY or MARGIN
    to_product_type: str  # CNC or MARGIN


@dataclass(frozen=True, slots=True)
class ConvertPositionResult:
    """Result of a position conversion."""

    success: bool = False
    message: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConvertPositionResult:
        return cls(
            success=bool(data.get("success", False)),
            message=str(data.get("message", "")),
        )


class DhanConvertPosition:
    """Position conversion for Dhan (intraday ↔ delivery).

    Usage::

        converter = DhanConvertPosition(client=dhan_client)
        result = converter.convert(ConvertPositionRequest(...))
    """

    def __init__(self, *, client: BaseHttpClient) -> None:
        self._client = client

    def convert(self, request: ConvertPositionRequest) -> ConvertPositionResult:
        """Convert a position between product types."""
        payload = {
            "dhanClientId": self._client.client_id,
            "securityId": request.security_id,
            "exchangeSegment": request.exchange_segment,
            "positionType": request.position_type,
            "convertQty": request.convert_qty,
            "fromProductType": request.from_product_type,
            "toProductType": request.to_product_type,
        }
        logger.info(
            "dhan_convert_position",
            security_id=request.security_id,
            from_type=request.from_product_type,
            to_type=request.to_product_type,
        )
        data = self._client.post("/positions/convert", json=payload)
        raw = data.get("data", data) if isinstance(data, dict) else {}
        return ConvertPositionResult.from_dict(raw if isinstance(raw, dict) else {})


__all__ = ["DhanConvertPosition", "ConvertPositionRequest", "ConvertPositionResult"]
