"""Value objects — immutable, self-validating financial primitives.

These form the building blocks of the domain model.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from tradex.domain.enums import (
    Exchange,
    ExchangeSegment,
    InstrumentType,
    OptionType,
)


@dataclass(frozen=True)
class Money:
    """Immutable monetary value with currency.

    A value object representing a monetary amount with a currency code.
    Supports arithmetic operations, comparisons, and formatting.
    Amounts are always rounded to 2 decimal places (paise precision).

    Attributes:
        amount: The monetary amount as a Decimal.
        currency: ISO 4217 currency code. Defaults to "INR".

    Usage:
        price = Money(Decimal("2450.50"))
        total = price * 10
        print(total)  # ₹24,505.00

    Raises:
        ValueError: When performing operations on different currencies.
    """

    amount: Decimal
    currency: str = "INR"

    def __post_init__(self) -> None:
        if isinstance(self.amount, (int, float)):
            object.__setattr__(self, "amount", Decimal(str(self.amount)))
        object.__setattr__(
            self, "amount", self.amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        )

    def __add__(self, other: Money) -> Money:
        if self.currency != other.currency:
            raise ValueError(
                f"Cannot add different currencies: {self.currency} and {other.currency}"
            )
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: Money) -> Money:
        if self.currency != other.currency:
            raise ValueError(
                f"Cannot subtract different currencies: {self.currency} and {other.currency}"
            )
        return Money(self.amount - other.amount, self.currency)

    def __mul__(self, factor: int | float | Decimal) -> Money:
        return Money(self.amount * Decimal(str(factor)), self.currency)

    def __lt__(self, other: Money) -> bool:
        if self.currency != other.currency:
            raise ValueError("Cannot compare different currencies")
        return self.amount < other.amount

    def __le__(self, other: Money) -> bool:
        if self.currency != other.currency:
            raise ValueError("Cannot compare different currencies")
        return self.amount <= other.amount

    def __gt__(self, other: Money) -> bool:
        return not self.__le__(other)

    def __ge__(self, other: Money) -> bool:
        return not self.__lt__(other)

    @classmethod
    def zero(cls, currency: str = "INR") -> Money:
        """Create a zero-value Money instance.

        Args:
            currency: Currency code. Defaults to "INR".

        Returns:
            A Money instance with amount 0.
        """
        return cls(Decimal("0"), currency)

    @property
    def is_positive(self) -> bool:
        """Whether the amount is positive (> 0).

        Returns:
            True if amount is greater than zero.
        """
        return self.amount > 0

    @property
    def is_negative(self) -> bool:
        """Whether the amount is negative (< 0).

        Returns:
            True if amount is less than zero.
        """
        return self.amount < 0

    def to_paise(self) -> int:
        """Convert to paise (smallest INR unit).

        Useful for APIs that require integer paise amounts.

        Returns:
            Amount in paise as an integer.
        """
        return int(self.amount * 100)

    def __str__(self) -> str:
        return (
            f"₹{self.amount:,.2f}"
            if self.currency == "INR"
            else f"{self.currency} {self.amount:,.2f}"
        )


@dataclass(frozen=True)
class Price:
    """Price with automatic tick-size alignment.

    Ensures the price value is always aligned to the instrument's
    tick size (minimum price movement). For example, NSE equity
    has a tick size of ₹0.05, so prices are rounded to the
    nearest 0.05.

    Attributes:
        value: The aligned price as a Decimal.
        tick_size: Minimum price movement. Defaults to 0.05.

    Usage:
        price = Price.from_float(2450.33)  # Aligned to 2450.35
        print(price.as_float)  # 2450.35
    """

    value: Decimal
    tick_size: Decimal = Decimal("0.05")

    def __post_init__(self) -> None:
        if isinstance(self.value, (int, float)):
            object.__setattr__(self, "value", Decimal(str(self.value)))
        if isinstance(self.tick_size, (int, float)):
            object.__setattr__(self, "tick_size", Decimal(str(self.tick_size)))
        if self.tick_size > 0:
            aligned = (self.value / self.tick_size).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            ) * self.tick_size
            object.__setattr__(self, "value", aligned)

    @classmethod
    def from_float(cls, value: float, tick_size: float = 0.05) -> Price:
        """Create a Price from a float value.

        Args:
            value: Price value as a float.
            tick_size: Minimum price movement. Defaults to 0.05.

        Returns:
            Price instance with the value aligned to tick size.
        """
        return cls(Decimal(str(value)), Decimal(str(tick_size)))

    @property
    def as_float(self) -> float:
        """Get the price as a float.

        Returns:
            Price value as a Python float.
        """
        return float(self.value)

    def __lt__(self, other: Price) -> bool:
        return self.value < other.value

    def __le__(self, other: Price) -> bool:
        return self.value <= other.value

    def __gt__(self, other: Price) -> bool:
        return self.value > other.value

    def __ge__(self, other: Price) -> bool:
        return self.value >= other.value

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class Quantity:
    """Quantity with automatic lot-size alignment.

    Ensures the quantity is always a valid multiple of the
    instrument's lot size. F&O instruments trade in lot sizes
    (e.g., NIFTY lot = 50), so quantities must be multiples.

    Attributes:
        value: The aligned quantity in shares/lots.
        lot_size: Minimum trading lot. Defaults to 1.

    Usage:
        qty = Quantity.from_lots(3, lot_size=50)  # 150 shares
        print(qty.lots)  # 3

    Raises:
        ValueError: If quantity is not a multiple of lot_size.
    """

    value: int
    lot_size: int = 1

    def __post_init__(self) -> None:
        if self.lot_size > 0 and self.value % self.lot_size != 0:
            raise ValueError(f"Quantity {self.value} is not a multiple of lot size {self.lot_size}")

    @classmethod
    def from_lots(cls, lots: int, lot_size: int) -> Quantity:
        """Create a Quantity from a number of lots.

        Args:
            lots: Number of lots.
            lot_size: Shares per lot.

        Returns:
            Quantity with total shares = lots * lot_size.

        Raises:
            ValueError: If lots is negative.
        """
        return cls(lots * lot_size, lot_size)

    @property
    def lots(self) -> int:
        """Get the quantity expressed in lots.

        Returns:
            Number of complete lots. Returns 0 if lot_size is 0.
        """
        if self.lot_size == 0:
            return 0
        return self.value // self.lot_size

    def __add__(self, other: Quantity) -> Quantity:
        if self.lot_size != other.lot_size:
            raise ValueError("Cannot add quantities with different lot sizes")
        return Quantity(self.value + other.value, self.lot_size)

    def __sub__(self, other: Quantity) -> Quantity:
        if self.lot_size != other.lot_size:
            raise ValueError("Cannot subtract quantities with different lot sizes")
        return Quantity(self.value - other.value, self.lot_size)

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class DateRange:
    """Immutable date range for historical queries.

    Represents a contiguous date range with validation that
    start <= end. Provides convenience constructors for common
    ranges like "today" or "last N days".

    Attributes:
        start: Start date (inclusive).
        end: End date (inclusive).

    Usage:
        range = DateRange.last_days(30)
        print(range.days)  # 30

    Raises:
        ValueError: If start date is after end date.
    """

    start: date
    end: date

    def __post_init__(self) -> None:
        if self.start > self.end:
            raise ValueError(f"Start date {self.start} is after end date {self.end}")

    @classmethod
    def today(cls) -> DateRange:
        """Create a date range for today only.

        Returns:
            DateRange where both start and end are today.
        """
        d = date.today()
        return cls(d, d)

    @classmethod
    def last_days(cls, days: int) -> DateRange:
        """Create a date range for the last N days.

        Args:
            days: Number of days to look back (inclusive).

        Returns:
            DateRange from (today - days) to today.
        """
        from datetime import timedelta

        end = date.today()
        start = end - timedelta(days=days)
        return cls(start, end)

    @property
    def days(self) -> int:
        """Total number of days in the range (inclusive).

        Returns:
            Number of days from start to end, inclusive.
        """
        return (self.end - self.start).days + 1

    def contains(self, d: date) -> bool:
        """Check if a date falls within the range.

        Args:
            d: The date to check.

        Returns:
            True if start <= d <= end.
        """
        return self.start <= d <= self.end


@dataclass(frozen=True)
class SecurityID:
    """Canonical security identifier — not broker-specific.

    A broker-agnostic identifier for a security, optionally
    tagged with the exchange it belongs to.

    Attributes:
        value: The security ID string.
        exchange: The exchange this ID belongs to.
    """

    value: str
    exchange: Exchange = Exchange.UNKNOWN

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class InstrumentKey:
    """Complete instrument key for derivative resolution.

    Uniquely identifies any instrument including derivatives.
    The combination of symbol + exchange + instrument_type +
    expiry + strike + option_type forms a unique key.

    Attributes:
        symbol: Trading symbol (e.g., "NIFTY").
        exchange: Exchange (NSE, BSE, MCX).
        instrument_type: Instrument type (EQUITY, FUTIDX, OPTIDX, etc.).
        expiry: Expiry date (for derivatives).
        strike: Strike price (for options).
        option_type: CALL or PUT (for options).
    """

    symbol: str
    exchange: Exchange
    instrument_type: InstrumentType
    expiry: Optional[date] = None
    strike: Optional[Decimal] = None
    option_type: Optional[OptionType] = None

    def __str__(self) -> str:
        parts = [self.symbol, self.exchange.value, self.instrument_type.value]
        if self.expiry:
            parts.append(self.expiry.isoformat())
        if self.strike is not None:
            parts.append(str(self.strike))
        if self.option_type:
            parts.append(self.option_type.value)
        return ":".join(parts)


@dataclass(frozen=True)
class ExpiryDate:
    """Expiry date with weekly/monthly flag.

    Attributes:
        date: The expiry date.
        flag: "W" for weekly expiry, "M" for monthly.
    """

    date: date
    flag: Optional[str] = None  # "W" or "M"

    @property
    def is_weekly(self) -> bool:
        return self.flag == "W"

    @property
    def is_monthly(self) -> bool:
        return self.flag == "M"


@dataclass(frozen=True)
class TickSize:
    """Tick size configuration per exchange segment.

    Different exchange segments have different minimum price
    movements (tick sizes). For example, NSE equity uses 0.05,
    while BSE equity uses 0.01.

    Attributes:
        segment: The exchange segment.
        tick_size: Minimum price movement for this segment.
    """

    segment: ExchangeSegment
    tick_size: Decimal = Decimal("0.05")

    @classmethod
    def for_segment(cls, segment: ExchangeSegment) -> TickSize:
        """Get the default tick size for an exchange segment.

        Args:
            segment: The exchange segment to get tick size for.

        Returns:
            TickSize with the segment's default tick size.
        """
        defaults = {
            ExchangeSegment.NSE_EQ: Decimal("0.05"),
            ExchangeSegment.BSE_EQ: Decimal("0.01"),
            ExchangeSegment.NSE_FNO: Decimal("0.05"),
            ExchangeSegment.BSE_FNO: Decimal("0.05"),
            ExchangeSegment.MCX_COMM: Decimal("0.01"),
            ExchangeSegment.NSE_CURRENCY: Decimal("0.0025"),
            ExchangeSegment.BSE_CURRENCY: Decimal("0.0025"),
        }
        return cls(segment=segment, tick_size=defaults.get(segment, Decimal("0.05")))
