"""Upstox broker adapter — translate between InstrumentId and Upstox-native formats."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from domain.instrument_id import InstrumentId
from domain.symbols import normalize_exchange, normalize_symbol


def to_instrument_id(
    symbol: str = "",
    trading_symbol: str = "",
    instrument_key: str = "",
    exchange: str = "",
    exchange_segment: str = "",
    instrument_type: str = "",
    option_type: str | None = None,
    strike: float | None = None,
    expiry: str | None = None,
    underlying_symbol: str | None = None,
) -> InstrumentId:
    """Convert Upstox instrument fields to canonical InstrumentId.

    Upstox uses:
    - instrument_key: wire format (e.g., "NSE_FO|NIFTY22MAY2524000CE")
    - symbol: canonical symbol (e.g., "NIFTY22MAY2524000CE")
    - trading_symbol: display symbol (e.g., "NIFTY 22 MAY 25 24000 CE")
    - exchange_segment: "NSE_EQ", "NSE_FO", "MCX_FUT"
    - instrument_type: "EQ", "FUTIDX", "OPTIDX"
    """
    # Determine exchange from segment
    exch = exchange or _segment_to_exchange(exchange_segment)

    # Determine underlying
    und = underlying_symbol or symbol or trading_symbol
    if not und and instrument_key:
        # Parse from instrument_key: "NSE_FO|NIFTY22MAY2524000CE" → "NIFTY"
        parts = instrument_key.split("|")
        if len(parts) > 1:
            und = _extract_underlying_from_key(parts[1])

    # Parse expiry
    expiry_date = None
    if expiry:
        for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d%b%Y"):
            try:
                expiry_date = datetime.strptime(expiry, fmt).date()
                break
            except ValueError:
                continue

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
        exchange=normalize_exchange(exch),
        underlying=normalize_symbol(und),
        expiry=expiry_date,
        strike=Decimal(str(strike)) if strike is not None else None,
        right=right,
    )


def from_instrument_id(iid: InstrumentId) -> dict:
    """Convert canonical InstrumentId to Upstox API parameters.

    Returns dict with keys matching Upstox's instrument resolution.
    """
    result = {
        "symbol": iid.underlying,
        "exchange_segment": _exchange_to_segment(iid.exchange),
    }

    if iid.expiry:
        result["expiry"] = iid.expiry.strftime("%Y-%m-%d")

    if iid.strike is not None:
        result["strike"] = float(iid.strike)

    if iid.right:
        if iid.right in ("CE", "PE"):
            result["option_type"] = iid.right
        elif iid.right == "FUT":
            result["instrument_type"] = "FUT"

    return result


def _segment_to_exchange(segment: str) -> str:
    """Convert Upstox exchange_segment to canonical exchange."""
    segment = segment.upper()
    mapping = {
        "NSE_EQ": "NSE",
        "BSE_EQ": "BSE",
        "NSE_FO": "NFO",
        "BSE_FO": "BSE_FNO",
        "MCX_FUT": "MCX",
        "NSE_INDEX": "NSE",
    }
    return mapping.get(segment, "NSE")


def _exchange_to_segment(exchange: str) -> str:
    """Convert canonical exchange to Upstox exchange_segment."""
    exchange = exchange.upper()
    mapping = {
        "NSE": "NSE_EQ",
        "BSE": "BSE_EQ",
        "NFO": "NSE_FO",
        "MCX": "MCX_FUT",
        "BSE_FNO": "BSE_FO",
    }
    return mapping.get(exchange, "NSE_EQ")


def _extract_underlying_from_key(key: str) -> str:
    """Extract underlying from Upstox instrument key.

    E.g., "NIFTY22MAY2524000CE" → "NIFTY"
          "RELIANCE" → "RELIANCE"
    """
    # Remove date and strike patterns
    # NIFTY22MAY2524000CE → extract NIFTY
    import re
    match = re.match(r"^([A-Z]+)", key)
    return match.group(1) if match else key
