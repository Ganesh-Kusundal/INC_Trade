"""Account aggregate — owns credentials, profile, and fund limits."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional



@dataclass
class FundLimits:
    """Fund limits snapshot."""

    available_balance: Decimal = Decimal("0")
    sod_limit: Decimal = Decimal("0")
    collateral: Decimal = Decimal("0")
    receivable: Decimal = Decimal("0")
    utilized: Decimal = Decimal("0")
    blocked_payout: Decimal = Decimal("0")
    withdrawable: Decimal = Decimal("0")
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dhan(cls, data: dict[str, Any]) -> FundLimits:
        """Construct from Dhan API response."""
        return cls(
            available_balance=Decimal(str(data.get("availabelBalance", 0))),
            sod_limit=Decimal(str(data.get("sodLimit", 0))),
            collateral=Decimal(str(data.get("collateralAmount", 0))),
            receivable=Decimal(str(data.get("receiveableAmount", 0))),
            utilized=Decimal(str(data.get("utilizedAmount", 0))),
            blocked_payout=Decimal(str(data.get("blockedPayoutAmount", 0))),
            withdrawable=Decimal(str(data.get("withdrawableBalance", 0))),
            raw=data,
        )

    @property
    def net_available(self) -> Decimal:
        """Balance available for trading."""
        return self.available_balance + self.collateral - self.blocked_payout


@dataclass
class AccountProfile:
    """Broker account profile."""

    client_id: str = ""
    name: str = ""
    email: str = ""
    phone: str = ""
    pan: str = ""
    active_segments: list[str] = field(default_factory=list)
    ddpi_enabled: bool = False
    mtf_enabled: bool = False
    data_plan_active: bool = False
    data_validity: str = ""
    token_validity: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dhan(cls, data: dict[str, Any]) -> AccountProfile:
        """Construct from Dhan profile API response."""
        return cls(
            client_id=str(data.get("dhanClientId", "")),
            name=data.get("fullName", ""),
            email=data.get("email", ""),
            phone=data.get("mobileNumber", ""),
            pan=data.get("pan", ""),
            active_segments=data.get("activeSegment", "").split(",")
            if data.get("activeSegment")
            else [],
            ddpi_enabled=bool(data.get("ddpi")),
            mtf_enabled=bool(data.get("mtf")),
            data_plan_active=bool(data.get("dataPlan")),
            data_validity=str(data.get("dataValidity", "")),
            token_validity=str(data.get("tokenValidity", "")),
            raw=data,
        )

    def has_segment(self, segment: str) -> bool:
        """Check if a segment is active."""
        return segment in self.active_segments

    @property
    def can_trade(self) -> bool:
        """Whether the account is set up for trading."""
        return bool(self.client_id) and len(self.active_segments) > 0


@dataclass
class Account:
    """Account aggregate root.

    Owns the broker account profile and fund limits.
    """

    account_id: str
    broker_name: str
    profile: AccountProfile = field(default_factory=AccountProfile)
    fund_limits: Optional[FundLimits] = None
    connected: bool = False
    connected_at: Optional[datetime] = None

    def has_segment(self, segment: str) -> bool:
        """Check if the account has access to a segment."""
        return self.profile.has_segment(segment)

    @property
    def available_balance(self) -> Decimal:
        """Available balance for trading."""
        if self.fund_limits:
            return self.fund_limits.net_available
        return Decimal("0")

    @property
    def can_trade(self) -> bool:
        """Whether the account is ready for trading."""
        return self.connected and self.profile.can_trade

    def __str__(self) -> str:
        status = "connected" if self.connected else "disconnected"
        return f"Account({self.broker_name}:{self.account_id} [{status}])"
