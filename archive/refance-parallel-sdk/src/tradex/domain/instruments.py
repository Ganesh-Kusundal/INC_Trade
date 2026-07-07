"""Instrument hierarchy — equities, futures, options, indices."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Optional

from tradex.domain.enums import (
    Exchange,
    ExchangeSegment,
    InstrumentType,
    OptionType,
)
from tradex.domain.value_objects import ExpiryDate, InstrumentKey


@dataclass
class Instrument:
    """Base instrument — the root of the instrument hierarchy.

    Represents any tradeable instrument with its metadata including
    security IDs, exchange information, lot size, and tick size.
    Subclass this for specialized instrument types.

    Attributes:
        security_id: Broker-assigned unique security identifier.
        trading_symbol: Canonical trading symbol.
        display_symbol: Human-readable display name.
        exchange: Exchange (NSE, BSE, MCX).
        exchange_segment: Exchange segment with product type.
        instrument_type: Instrument classification (EQUITY, INDEX, FUTIDX, etc.).
        isin: International Securities Identification Number.
        lot_size: Minimum trading lot (1 for equities, varies for F&O).
        tick_size: Minimum price movement.
        freeze_quantity: Maximum order quantity before freeze.
        raw: Raw broker security master data.

    Usage:
        instrument = await platform.resolve_instrument("RELIANCE")
        quote = await platform.get_quote(instrument)
        order = await platform.place_order(instrument=instrument, ...)
    """

    security_id: str
    trading_symbol: str = ""
    display_symbol: str = ""
    exchange: Exchange = Exchange.NSE
    exchange_segment: ExchangeSegment = ExchangeSegment.NSE_EQ
    instrument_type: InstrumentType = InstrumentType.UNKNOWN
    isin: str = ""
    lot_size: int = 1
    tick_size: Decimal = Decimal("0.05")
    freeze_quantity: int = 0
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dhan_master(cls, data: dict[str, Any]) -> Instrument:
        """Construct from a Dhan security master CSV row.

        Parses the Dhan security master format with SEM_* prefixed
        fields and maps exchange/instrument strings to enums.

        Args:
            data: Dict with SEM_EXM_EXCH_ID, SEM_INSTRUMENT_NAME,
                SEM_SMST_SECURITY_ID, SEM_TRADING_SYMBOL, etc.

        Returns:
            Populated Instrument with all fields mapped.
        """
        exchange_map = {
            "NSE": Exchange.NSE,
            "BSE": Exchange.BSE,
            "MCX": Exchange.MCX,
        }
        instrument_map = {
            "EQUITY": InstrumentType.EQUITY,
            "INDEX": InstrumentType.INDEX,
            "FUTIDX": InstrumentType.FUTIDX,
            "FUTSTK": InstrumentType.FUTSTK,
            "OPTIDX": InstrumentType.OPTIDX,
            "OPTSTK": InstrumentType.OPTSTK,
            "FUTCOM": InstrumentType.FUTCOM,
            "OPTFUT": InstrumentType.OPTFUT,
            "FUTCUR": InstrumentType.FUTCUR,
            "OPTCUR": InstrumentType.OPTCUR,
        }
        segment_map = {
            ("NSE", "EQUITY"): ExchangeSegment.NSE_EQ,
            ("BSE", "EQUITY"): ExchangeSegment.BSE_EQ,
            ("NSE", "INDEX"): ExchangeSegment.INDEX,
            ("NSE", "FUTIDX"): ExchangeSegment.NSE_FNO,
            ("NSE", "OPTIDX"): ExchangeSegment.NSE_FNO,
            ("NSE", "FUTSTK"): ExchangeSegment.NSE_FNO,
            ("NSE", "OPTSTK"): ExchangeSegment.NSE_FNO,
            ("BSE", "FUTIDX"): ExchangeSegment.BSE_FNO,
            ("BSE", "OPTIDX"): ExchangeSegment.BSE_FNO,
            ("MCX", "FUTCOM"): ExchangeSegment.MCX_COMM,
            ("MCX", "OPTFUT"): ExchangeSegment.MCX_COMM,
        }

        exch_str = data.get("SEM_EXM_EXCH_ID", "")
        instr_str = data.get("SEM_INSTRUMENT_NAME", "")

        return cls(
            security_id=str(data.get("SEM_SMST_SECURITY_ID", "")),
            trading_symbol=data.get("SEM_TRADING_SYMBOL", ""),
            display_symbol=data.get("SEM_CUSTOM_SYMBOL", ""),
            exchange=exchange_map.get(exch_str, Exchange.UNKNOWN),
            exchange_segment=segment_map.get((exch_str, instr_str), ExchangeSegment.NSE_EQ),
            instrument_type=instrument_map.get(instr_str, InstrumentType.UNKNOWN),
            lot_size=int(data.get("SEM_LOT_UNITS", 1)),
            tick_size=Decimal(str(data.get("SEM_TICK_SIZE", "0.05"))),
            freeze_quantity=int(data.get("SEM_FREEZE_QTY", 0)),
            raw=data,
        )

    def to_key(self) -> InstrumentKey:
        """Convert to an InstrumentKey for derivative resolution.

        Returns:
            InstrumentKey with symbol, exchange, and instrument_type.
        """
        return InstrumentKey(
            symbol=self.trading_symbol,
            exchange=self.exchange,
            instrument_type=self.instrument_type,
        )

    def __str__(self) -> str:
        return f"{self.display_symbol or self.trading_symbol} ({self.exchange.value})"


@dataclass
class Equity(Instrument):
    """Equity instrument — shares listed on NSE or BSE.

    Subclass of Instrument that automatically sets the instrument
    type to EQUITY.
    """

    def __post_init__(self) -> None:
        self.instrument_type = InstrumentType.EQUITY


@dataclass
class Index(Instrument):
    """Index instrument — market indices like NIFTY 50, BANKNIFTY.

    Subclass of Instrument that sets instrument type to INDEX
    and exchange segment to IDX_I. Use the built-in BUILTIN_INSTRUMENTS
    dict for common indices.
    """

    def __post_init__(self) -> None:
        self.instrument_type = InstrumentType.INDEX
        self.exchange_segment = ExchangeSegment.INDEX


@dataclass
class Future(Instrument):
    """Future contract — F&O futures for equities or indices.

    Extends Instrument with an expiry date. Supports both
    index futures (FUTIDX) and stock futures (FUTSTK).

    Attributes:
        expiry: Expiry date with weekly/monthly flag.
    """

    expiry: Optional[ExpiryDate] = None

    def __post_init__(self) -> None:
        if self.instrument_type == InstrumentType.UNKNOWN:
            self.instrument_type = InstrumentType.FUTIDX

    def to_key(self) -> InstrumentKey:
        """Convert to an InstrumentKey including the expiry date.

        Returns:
            InstrumentKey with symbol, exchange, type, and expiry.
        """
        return InstrumentKey(
            symbol=self.trading_symbol,
            exchange=self.exchange,
            instrument_type=self.instrument_type,
            expiry=self.expiry.date if self.expiry else None,
        )


@dataclass
class Option(Instrument):
    """Option contract — calls and puts for equities or indices.

    Extends Instrument with expiry, strike, and option type.
    Supports both index options (OPTIDX) and stock options (OPTSTK).

    Attributes:
        expiry: Expiry date with weekly/monthly flag.
        strike: Strike price.
        option_type: CALL or PUT.
    """

    expiry: Optional[ExpiryDate] = None
    strike: Optional[Decimal] = None
    option_type: Optional[OptionType] = None

    def __post_init__(self) -> None:
        if self.instrument_type == InstrumentType.UNKNOWN:
            self.instrument_type = InstrumentType.OPTIDX

    def to_key(self) -> InstrumentKey:
        """Convert to an InstrumentKey including expiry, strike, type.

        Returns:
            Complete InstrumentKey for derivative resolution.
        """
        return InstrumentKey(
            symbol=self.trading_symbol,
            exchange=self.exchange,
            instrument_type=self.instrument_type,
            expiry=self.expiry.date if self.expiry else None,
            strike=self.strike,
            option_type=self.option_type,
        )

    @property
    def is_call(self) -> bool:
        """Whether this is a call option.

        Returns:
            True if option_type is CALL.
        """
        return self.option_type == OptionType.CALL

    @property
    def is_put(self) -> bool:
        """Whether this is a put option.

        Returns:
            True if option_type is PUT.
        """
        return self.option_type == OptionType.PUT


@dataclass
class Spot(Instrument):
    """Spot instrument — cash market spot price reference.

    Represents the current spot price of an instrument, used
    as the underlying reference for derivatives pricing.

    Spot instruments are not directly tradeable but serve as
    the price reference for option chain analysis, margin
    calculations, and derivative contract resolution.

    Attributes:
        underlying: The underlying instrument this spot refers to.
        last_price: Current spot price.
        previous_close: Previous session close price.
    """

    last_price: Decimal = Decimal("0")
    previous_close: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if self.instrument_type == InstrumentType.UNKNOWN:
            self.instrument_type = InstrumentType.INDEX

    @property
    def change(self) -> Decimal:
        """Price change from previous close."""
        return self.last_price - self.previous_close

    @property
    def change_pct(self) -> Decimal:
        """Percentage change from previous close."""
        if self.previous_close == 0:
            return Decimal("0")
        return ((self.last_price - self.previous_close) / self.previous_close) * 100


# --- Quick-reference instruments ---

BUILTIN_INSTRUMENTS = {
    "NIFTY": Index(
        security_id="13",
        trading_symbol="NIFTY",
        display_symbol="NIFTY 50",
        exchange=Exchange.INDEX,
        lot_size=50,
        tick_size=Decimal("0.05"),
    ),
    "BANKNIFTY": Index(
        security_id="25",
        trading_symbol="BANKNIFTY",
        display_symbol="BANK NIFTY",
        exchange=Exchange.INDEX,
        lot_size=15,
        tick_size=Decimal("0.05"),
    ),
    "FINNIFTY": Index(
        security_id="27",
        trading_symbol="FINNIFTY",
        display_symbol="FINNIFTY",
        exchange=Exchange.INDEX,
        lot_size=40,
        tick_size=Decimal("0.05"),
    ),
    "MIDCPNIFTY": Index(
        security_id="442",
        trading_symbol="MIDCPNIFTY",
        display_symbol="MIDCP NIFTY",
        exchange=Exchange.INDEX,
        lot_size=75,
        tick_size=Decimal("0.05"),
    ),
    "SENSEX": Index(
        security_id="51",
        trading_symbol="SENSEX",
        display_symbol="SENSEX",
        exchange=Exchange.BSE,
        exchange_segment=ExchangeSegment.INDEX,
        lot_size=10,
        tick_size=Decimal("0.05"),
    ),
}
