"""EdisProvider extension interface.

Capability gate: ``BrokerCapabilities`` edis field
Supported by: Dhan (EDIS/TPIN for CNC delivery sell authorization)
Not supported by: Upstox
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class EdisRequest:
    """EDIS authorization request for delivery sell."""

    isin: str
    quantity: int
    exchange: str


@dataclass(frozen=True)
class EdisResult:
    """Result of EDIS authorization or status check."""

    success: bool
    isin: str
    status: str = ""
    message: str = ""
    edis_id: str = ""


class EdisProvider(Protocol):
    """Extension interface for EDIS / TPIN delivery authorization.

    Required for CNC (delivery) sell operations on Dhan.
    """

    async def generate_edis_tpin(
        self,
        *,
        quota: object,
    ) -> EdisResult:
        """Trigger TPIN generation for EDIS."""
        ...

    async def authorize_edis(
        self,
        requests: list[EdisRequest],
        *,
        quota: object,
    ) -> EdisResult:
        """Submit EDIS authorization for a list of holdings."""
        ...

    async def get_edis_status(
        self,
        isin: str,
        *,
        quota: object,
    ) -> EdisResult:
        """Check EDIS authorization status."""
        ...
