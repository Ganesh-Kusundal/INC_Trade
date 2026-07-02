"""Common broker adapter — translate between InstrumentId and common Instrument."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from brokers.common.instruments import Instrument
from domain import InstrumentType
from domain.entities.instrument import Instrument as DomainInstrument
from domain.instrument_id import InstrumentId
from domain.symbols import normalize_exchange, normalize_symbol


def to_instrument_id(instrument: Instrument) -> InstrumentId:
    """Convert common Instrument to canonical InstrumentId.

    Examples:
        Instrument("RELIANCE", "NSE", EQUITY) → NSE:RELIANCE
        Instrument("NIFTY", "NFO", OPTIONS, expiry="2026-07-30", strike=25000, option_type="CE")
            → NFO:NIFTY:20260730:25000:CE
    """
    expiry = date.fromisoformat(instrument.expiry) if instrument.expiry else None
    right = None
    if instrument.option_type:
        right = instrument.option_type.upper()
    elif instrument.asset_class == InstrumentType.FUTURES:
        right = "FUT"

    return InstrumentId(
        exchange=normalize_exchange(instrument.exchange),
        underlying=normalize_symbol(instrument.symbol),
        expiry=expiry,
        strike=instrument.strike,
        right=right,
    )


def from_instrument_id(iid: InstrumentId) -> Instrument:
    """Convert canonical InstrumentId to common Instrument.

    Note: broker_identifier and broker_symbol are not populated —
    those require broker-specific resolution.
    """
    from brokers.common.instruments import Instrument as CommonInstrument

    asset_class = InstrumentType.EQUITY
    if iid.is_future:
        asset_class = InstrumentType.FUTURES
    elif iid.is_option:
        asset_class = InstrumentType.OPTIONS
    elif iid.is_index:
        asset_class = InstrumentType.INDEX

    domain_inst = DomainInstrument(
        symbol=iid.underlying,
        exchange=iid.exchange,
        security_id="",
        instrument_type=asset_class.value,
        lot_size=0,
        tick_size=Decimal("0"),
        option_type=iid.right if iid.right in ("CE", "PE") else None,
        strike_price=iid.strike,
        expiry=iid.expiry.isoformat() if iid.expiry else None,
    )

    return CommonInstrument(
        domain_instrument=domain_inst,
        asset_class=asset_class,
    )
