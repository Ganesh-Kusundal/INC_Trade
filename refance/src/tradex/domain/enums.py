"""All enumerations used across the SDK.

These are broker-agnostic. Providers map their own values to these.
"""

from __future__ import annotations

from enum import Enum, IntEnum


class Exchange(str, Enum):
    """Canonical exchange identifiers."""

    NSE = "NSE"
    BSE = "BSE"
    MCX = "MCX"
    INDEX = "INDEX"
    CURRENCY = "CURRENCY"
    UNKNOWN = "UNKNOWN"


class ExchangeSegment(str, Enum):
    """Exchange segment with product type."""

    NSE_EQ = "NSE_EQ"
    BSE_EQ = "BSE_EQ"
    NSE_FNO = "NSE_FNO"
    BSE_FNO = "BSE_FNO"
    MCX_COMM = "MCX_COMM"
    NSE_CURRENCY = "NSE_CURRENCY"
    BSE_CURRENCY = "BSE_CURRENCY"
    INDEX = "IDX_I"


class InstrumentType(str, Enum):
    """Instrument classification."""

    EQUITY = "EQUITY"
    INDEX = "INDEX"
    FUTIDX = "FUTIDX"
    FUTSTK = "FUTSTK"
    OPTIDX = "OPTIDX"
    OPTSTK = "OPTSTK"
    FUTCOM = "FUTCOM"
    OPTFUT = "OPTFUT"
    FUTCUR = "FUTCUR"
    OPTCUR = "OPTCUR"
    UNKNOWN = "UNKNOWN"


class Side(str, Enum):
    """Order side."""

    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    """Order type."""

    LIMIT = "LIMIT"
    MARKET = "MARKET"
    STOP_LOSS = "STOP_LOSS"
    STOP_LOSS_MARKET = "STOP_LOSS_MARKET"


class ProductType(str, Enum):
    """Product type (margin treatment)."""

    CNC = "CNC"  # Cash and carry (delivery)
    INTRADAY = "INTRADAY"  # Intraday
    MARGIN = "MARGIN"  # Margin
    MTF = "MTF"  # Margin trading facility


class OrderStatus(str, Enum):
    """Order lifecycle status."""

    PENDING = "PENDING"
    PLACED = "PLACED"
    ACCEPTED = "ACCEPTED"
    OPEN = "OPEN"
    PART_TRADED = "PART_TRADED"
    TRADED = "TRADED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    TRIGGER_PENDING = "TRIGGER_PENDING"
    UNKNOWN = "UNKNOWN"


class Validity(str, Enum):
    """Order validity."""

    DAY = "DAY"
    IOC = "IOC"


class PositionType(str, Enum):
    """Position direction."""

    LONG = "LONG"
    SHORT = "SHORT"
    CLOSED = "CLOSED"


class OptionType(str, Enum):
    """Option type."""

    CALL = "CALL"
    PUT = "PUT"


class ExpiryFlag(str, Enum):
    """Expiry frequency."""

    WEEKLY = "W"
    MONTHLY = "M"


class MarketSession(str, Enum):
    """Market session state."""

    PRE_OPEN = "PRE_OPEN"
    OPEN = "OPEN"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"
    HOLIDAY = "HOLIDAY"


class SubscriptionType(IntEnum):
    """Market feed subscription types."""

    TICKER = 15
    QUOTE = 17
    DEPTH = 19
    FULL = 21


class OrderLegName(str, Enum):
    """Super order leg names."""

    ENTRY_LEG = "ENTRY_LEG"
    TARGET_LEG = "TARGET_LEG"
    STOP_LOSS_LEG = "STOP_LOSS_LEG"


class OrderFlag(str, Enum):
    """Order flag for forever orders."""

    SINGLE = "SINGLE"
    OCO = "OCO"


class AMOTime(str, Enum):
    """After market order timing."""

    OPEN = "OPEN"
    MARGIN_OPEN = "MARGIN_OPEN"


# --- Product type rules by segment ---

EQ_PRODUCT_TYPES = {ProductType.CNC, ProductType.INTRADAY, ProductType.MARGIN, ProductType.MTF}
FO_PRODUCT_TYPES = {ProductType.INTRADAY, ProductType.MARGIN}

SEGMENT_PRODUCT_MAP: dict[ExchangeSegment, set[ProductType]] = {
    ExchangeSegment.NSE_EQ: EQ_PRODUCT_TYPES,
    ExchangeSegment.BSE_EQ: EQ_PRODUCT_TYPES,
    ExchangeSegment.NSE_FNO: FO_PRODUCT_TYPES,
    ExchangeSegment.BSE_FNO: FO_PRODUCT_TYPES,
    ExchangeSegment.MCX_COMM: FO_PRODUCT_TYPES,
    ExchangeSegment.NSE_CURRENCY: FO_PRODUCT_TYPES,
    ExchangeSegment.BSE_CURRENCY: FO_PRODUCT_TYPES,
}
