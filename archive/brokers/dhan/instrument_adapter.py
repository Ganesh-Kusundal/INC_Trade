"""Dhan broker adapter — translate between InstrumentId and Dhan-native formats."""

from __future__ import annotations

from decimal import Decimal

from domain.instrument_id import InstrumentId
from domain.symbols import normalize_exchange, normalize_symbol


def to_instrument_id(
    symbol: str,
    exchange: str,
    security_id: str = "",
    instrument_type: str = "",
    option_type: str | None = None,
    strike_price: Decimal | None = None,
    expiry: str | None = None,
    underlying: str | None = None,
) -> InstrumentId:
    """Convert Dhan instrument fields to canonical InstrumentId.

    Dhan uses:
    - symbol: trading symbol (e.g., "NIFTY-26Jun2026-25000-CE")
    - exchange: "NSE", "NFO", "MCX"
    - security_id: numeric ID for API calls
    - instrument_type: "EQUITY", "OPTIDX", "FUTIDX", etc.
    - option_type: "CE" or "PE"
    - strike_price: strike price for options
    - expiry: date string for derivatives
    - underlying: parent symbol for derivatives
    """
    expiry_date = None
    if expiry:
        try:
            # Dhan uses various date formats
            for fmt in ("%d%b%Y", "%Y-%m-%d", "%d-%b-%Y"):
                try:
                    expiry_date = datetime.strptime(expiry, fmt).date()
                    break
                except ValueError:
                    continue
        except Exception:
            pass

    # Determine underlying
    und = underlying or symbol
    if expiry_date and not underlying:
        # Try to extract underlying from symbol
        # e.g., "NIFTY-26Jun2026-25000-CE" → "NIFTY"
        parts = symbol.split("-")
        if parts:
            und = parts[0]

    # Determine right
    right = None
    if option_type:
        right = option_type.upper()
        if right in ("CE", "CALL"):
            right = "CE"
        elif right in ("PE", "PUT"):
            right = "PE"
    elif instrument_type and "FUT" in instrument_type.upper():
        right = "FUT"

    return InstrumentId(
        exchange=normalize_exchange(exchange),
        underlying=normalize_symbol(und),
        expiry=expiry_date,
        strike=strike_price,
        right=right,
    )


def from_instrument_id(iid: InstrumentId) -> dict:
    """Convert canonical InstrumentId to Dhan API parameters.

    Returns dict with keys matching Dhan's order placement API.
    """
    result = {
        "symbol": iid.underlying,
        "exchange": iid.exchange,
    }

    if iid.expiry:
        result["expiry"] = iid.expiry.strftime("%d%b%Y")

    if iid.strike is not None:
        result["strike_price"] = str(iid.strike)

    if iid.right:
        if iid.right in ("CE", "PE"):
            result["right"] = iid.right
        elif iid.right == "FUT":
            result["instrument_type"] = "FUT"

    return result


# Needed for strptime
from datetime import datetime
