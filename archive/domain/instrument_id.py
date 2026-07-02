"""Canonical instrument identity — single source of truth.

Format: exchange:underlying:expiry:strike:right

Examples:
    NSE:RELIANCE                  (equity)
    NSE:NIFTY                     (index)
    NFO:NIFTY:20260730:FUT        (future)
    NFO:NIFTY:20260730:25000:CE   (option)

This is the universal identifier used across all internal modules:
market data, scanner, strategy, risk, OMS, portfolio, replay,
datalake, API, WebSocket, and broker adapters.

Broker-specific formats (RELIANCE-EQ, NIFTY-26Jun2026-25000-CE,
NSE_EQ|INE002A01018) are hidden inside broker adapters and never
leak across boundaries.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import ClassVar

from domain.symbols import normalize_exchange, normalize_symbol


@dataclass(frozen=True, order=True)
class InstrumentId:
    """Canonical instrument identity.

    Attributes:
        exchange: Exchange code (NSE, NFO, MCX, BSE).
        underlying: Underlying symbol (RELIANCE, NIFTY, CRUDEOIL).
        expiry: Expiry date (None for equities/indices).
        strike: Strike price (None for equities/indices/futures).
        right: Contract type (CE, PE, FUT, or None for equity/index).
    """

    exchange: str
    underlying: str
    expiry: date | None = None
    strike: Decimal | None = None
    right: str | None = None

    # Valid exchange codes
    VALID_EXCHANGES: ClassVar[frozenset[str]] = frozenset({"NSE", "BSE", "NFO", "MCX"})
    # Valid right values
    VALID_RIGHTS: ClassVar[frozenset[str]] = frozenset({"CE", "PE", "FUT"})

    def __post_init__(self):
        # Normalize strike to consistent Decimal form
        # Decimal(24000.0) != Decimal(24000), so normalize via string
        if self.strike is not None:
            object.__setattr__(self, "strike", Decimal(str(self.strike)))

        # Validate exchange
        if normalize_exchange(self.exchange) not in self.VALID_EXCHANGES:
            raise ValueError(f"Invalid exchange: {self.exchange!r}. Must be one of {self.VALID_EXCHANGES}")
        # Validate right if provided
        if self.right and self.right.upper() not in self.VALID_RIGHTS:
            raise ValueError(f"Invalid right: {self.right!r}. Must be one of {self.VALID_RIGHTS}")

    # ── Factory methods ───────────────────────────────────────────────────

    @classmethod
    def equity(cls, exchange: str, symbol: str) -> InstrumentId:
        """Create equity instrument ID: NSE:RELIANCE."""
        return cls(exchange=normalize_exchange(exchange), underlying=normalize_symbol(symbol))

    @classmethod
    def index(cls, exchange: str, name: str) -> InstrumentId:
        """Create index instrument ID: NSE:NIFTY."""
        return cls(exchange=normalize_exchange(exchange), underlying=normalize_symbol(name))

    @classmethod
    def future(cls, exchange: str, underlying: str, expiry: date) -> InstrumentId:
        """Create futures instrument ID: NFO:NIFTY:20260730:FUT."""
        return cls(
            exchange=normalize_exchange(exchange),
            underlying=normalize_symbol(underlying),
            expiry=expiry,
            right="FUT",
        )

    @classmethod
    def option(
        cls,
        exchange: str,
        underlying: str,
        expiry: date,
        strike: Decimal | float | int,
        right: str,
    ) -> InstrumentId:
        """Create option instrument ID: NFO:NIFTY:20260730:25000:CE."""
        return cls(
            exchange=normalize_exchange(exchange),
            underlying=normalize_symbol(underlying),
            expiry=expiry,
            strike=Decimal(str(strike)),
            right=normalize_symbol(right),
        )

    # ── Serialization ─────────────────────────────────────────────────────

    def __str__(self) -> str:
        """Serialize to canonical string format.

        Examples:
            NSE:RELIANCE
            NFO:NIFTY:20260730:FUT
            NFO:NIFTY:20260730:25000:CE
        """
        parts = [self.exchange, self.underlying]
        if self.expiry:
            parts.append(self.expiry.strftime("%Y%m%d"))
        if self.strike is not None:
            parts.append(str(int(self.strike)))
        if self.right:
            parts.append(self.right)
        return ":".join(parts)

    def __repr__(self) -> str:
        return f"InstrumentId({self})"

    # ── Deserialization ───────────────────────────────────────────────────

    @classmethod
    def parse(cls, s: str) -> InstrumentId:
        """Parse canonical string to InstrumentId.

        Examples:
            "NSE:RELIANCE" → InstrumentId(NSE, RELIANCE)
            "NFO:NIFTY:20260730:FUT" → InstrumentId(NFO, NIFTY, expiry=2026-07-30, right=FUT)
            "NFO:NIFTY:20260730:25000:CE" → InstrumentId(NFO, NIFTY, expiry, strike, CE)
        """
        parts = s.strip().split(":")
        if len(parts) < 2:
            raise ValueError(f"Invalid InstrumentId format: {s!r}. Expected at least 'EXCHANGE:UNDERLYING'")

        exchange = parts[0].upper()
        underlying = parts[1].upper()

        expiry = None
        strike = None
        right = None

        if len(parts) > 2 and parts[2]:
            # Try to parse as date (YYYYMMDD)
            if re.match(r"^\d{8}$", parts[2]):
                expiry = datetime.strptime(parts[2], "%Y%m%d").date()
            # Try to parse as FUT
            elif parts[2].upper() == "FUT":
                right = "FUT"

        if len(parts) > 3 and parts[3]:
            # Try to parse as strike price
            try:
                strike = Decimal(parts[3])
            except Exception:
                # Not a strike — might be right for futures
                if parts[3].upper() == "FUT":
                    right = "FUT"

        if len(parts) > 4 and parts[4]:
            right = parts[4].upper()

        # If we have expiry but no right, and it's not equity/index
        if expiry and not right:
            # Could be a future without explicit FUT suffix
            right = "FUT"

        return cls(
            exchange=exchange,
            underlying=underlying,
            expiry=expiry,
            strike=strike,
            right=right,
        )

    # ── Properties ────────────────────────────────────────────────────────

    @property
    def asset_type(self) -> str:
        """Determine asset type from fields."""
        if self.right == "FUT":
            return "FUTURES"
        if self.right in ("CE", "PE"):
            return "OPTIONS"
        if self.underlying in ("NIFTY", "BANKNIFTY", "FINNIFTY", "SENSEX", "MIDCPNIFTY"):
            return "INDEX"
        return "EQUITY"

    @property
    def is_equity(self) -> bool:
        return self.asset_type == "EQUITY"

    @property
    def is_index(self) -> bool:
        return self.asset_type == "INDEX"

    @property
    def is_future(self) -> bool:
        return self.asset_type == "FUTURES"

    @property
    def is_option(self) -> bool:
        return self.asset_type == "OPTIONS"

    @property
    def is_call(self) -> bool:
        return self.right == "CE"

    @property
    def is_put(self) -> bool:
        return self.right == "PE"

    @property
    def key(self) -> tuple[str, str, str | None, str | None, str | None]:
        """Hashable key for dict lookups."""
        # Normalize strike to integer string for consistent comparison
        strike_str = str(int(self.strike)) if self.strike is not None else None
        return (
            self.exchange,
            self.underlying,
            self.expiry.isoformat() if self.expiry else None,
            strike_str,
            self.right,
        )

    def __hash__(self) -> int:
        return hash(self.key)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, InstrumentId):
            return NotImplemented
        return self.key == other.key

    # ── Convenience ───────────────────────────────────────────────────────

    def with_expiry(self, expiry: date) -> InstrumentId:
        """Return new InstrumentId with different expiry."""
        return InstrumentId(
            exchange=self.exchange,
            underlying=self.underlying,
            expiry=expiry,
            strike=self.strike,
            right=self.right,
        )

    def with_strike(self, strike: Decimal | float | int) -> InstrumentId:
        """Return new InstrumentId with different strike."""
        return InstrumentId(
            exchange=self.exchange,
            underlying=self.underlying,
            expiry=self.expiry,
            strike=Decimal(str(strike)),
            right=self.right,
        )

    def to_equity(self) -> InstrumentId:
        """Convert to equity form (strip expiry/strike/right)."""
        return InstrumentId(exchange=self.exchange, underlying=self.underlying)
