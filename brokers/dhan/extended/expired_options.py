"""Dhan expired options — historical data for expired option contracts.

API: POST /charts/expired-options
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from brokers.infrastructure.http_client import BaseHttpClient
from brokers.infrastructure.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ExpiredOptionsRequest:
    """Request for expired options data."""

    security_id: int
    exchange_segment: str
    instrument_type: str  # OPTIDX, OPTSTK
    expiry_flag: str  # WEEK, MONTH
    expiry_code: int = 0
    strike: str = "ATM"  # ATM, ATM+N, ATM-N
    drv_option_type: str = "CALL"  # CALL or PUT
    required_data: list[str] = field(default_factory=lambda: ["open", "high", "low", "close", "volume", "oi"])
    from_date: str = ""
    to_date: str = ""
    interval: int = 1


@dataclass(frozen=True, slots=True)
class ExpiredOptionsResult:
    """Result of expired options data fetch."""

    timestamps: list[int] = field(default_factory=list)
    open: list[float] = field(default_factory=list)
    high: list[float] = field(default_factory=list)
    low: list[float] = field(default_factory=list)
    close: list[float] = field(default_factory=list)
    volume: list[int] = field(default_factory=list)
    oi: list[int] = field(default_factory=list)
    iv: list[float] = field(default_factory=list)
    spot: list[float] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExpiredOptionsResult:
        return cls(
            timestamps=list(data.get("timestamp", [])),
            open=[float(x) for x in data.get("open", [])],
            high=[float(x) for x in data.get("high", [])],
            low=[float(x) for x in data.get("low", [])],
            close=[float(x) for x in data.get("close", [])],
            volume=[int(x) for x in data.get("volume", [])],
            oi=[int(x) for x in data.get("oi", [])],
            iv=[float(x) for x in data.get("iv", [])],
            spot=[float(x) for x in data.get("spot", [])],
        )


class DhanExpiredOptions:
    """Expired options data for Dhan.

    Usage::

        exp = DhanExpiredOptions(client=dhan_client)
        result = exp.fetch(ExpiredOptionsRequest(...))
    """

    def __init__(self, *, client: BaseHttpClient) -> None:
        self._client = client

    def fetch(self, request: ExpiredOptionsRequest) -> ExpiredOptionsResult:
        """Fetch historical data for an expired option contract."""
        payload = {
            "securityId": request.security_id,
            "exchangeSegment": request.exchange_segment,
            "instrument": request.instrument_type,
            "expiryFlag": request.expiry_flag,
            "expiryCode": request.expiry_code,
            "strike": request.strike,
            "drvOptionType": request.drv_option_type,
            "requiredData": request.required_data,
            "fromDate": request.from_date,
            "toDate": request.to_date,
            "interval": request.interval,
        }
        logger.info(
            "dhan_expired_options_fetch",
            security_id=request.security_id,
            strike=request.strike,
        )
        data = self._client.post("/charts/expired-options", json=payload)
        raw = data.get("data", data) if isinstance(data, dict) else {}
        return ExpiredOptionsResult.from_dict(raw if isinstance(raw, dict) else {})


__all__ = ["DhanExpiredOptions", "ExpiredOptionsRequest", "ExpiredOptionsResult"]
