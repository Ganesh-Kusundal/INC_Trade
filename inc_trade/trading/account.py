"""Account aggregate — the trading entity that owns orders, positions, and portfolio.

An Account represents a trading account at a broker. It is the aggregate root
for the Trading bounded context. Orders are placed **through** an Account, not
through an Instrument.

Architecture:
    Account is a domain entity with identity (``account_id``). It owns
    behaviour via ``AccountHandle`` (returned by ``TradingContext``), which
    delegates to injected ports. The raw ``Account`` dataclass is immutable
    and has zero infrastructure dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AccountType(str, Enum):
    """Type of trading account."""

    MARGIN = "MARGIN"
    DELIVERY = "DELIVERY"
    INTRADAY = "INTRADAY"
    COMMODITY = "COMMODITY"
    CURRENCY = "CURRENCY"


class AccountStatus(str, Enum):
    """Lifecycle status of a trading account."""

    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    SUSPENDED = "SUSPENDED"
    CLOSED = "CLOSED"

    @property
    def can_trade(self) -> bool:
        return self is AccountStatus.ACTIVE

    @property
    def is_terminal(self) -> bool:
        return self is AccountStatus.CLOSED


@dataclass(frozen=True)
class Account:
    """Canonical domain entity — a single trading account.

    This is the aggregate root for the Trading bounded context. Every
    order, position, and holding is scoped to an Account.

    Attributes:
        account_id: Unique identifier (e.g., ``"dhan/default"``).
        broker_id: Broker this account belongs to (e.g., ``"dhan"``).
        name: Human-readable account name.
        type: Account type (margin, delivery, etc.).
        status: Current lifecycle status.
        client_id: Broker client/user identifier (optional).
    """

    account_id: str
    broker_id: str
    name: str = ""
    type: AccountType = AccountType.MARGIN
    status: AccountStatus = AccountStatus.ACTIVE
    client_id: str = ""

    def display_name(self) -> str:
        """Human-readable account identifier."""
        return self.name or f"{self.broker_id}:{self.account_id}"
