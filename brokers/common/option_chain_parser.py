"""Shared option chain parser — eliminates duplication between brokers.

Both DhanProvider and UpstoxProvider had ~50 lines of near-identical
option chain parsing logic.  This module provides a single canonical
implementation.

Usage::

    from brokers.common.option_chain_parser import parse_option_chain
    chain = parse_option_chain(raw_data, underlying, provider, expiry)
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from brokers.domain.enums import AssetClass, OptionType
from brokers.domain.option_chain import OptionChain, OptionContract


def parse_option_chain(
    raw_data: dict[str, Any] | list[Any],
    underlying: Any,  # Instrument (avoiding import)
    provider: Any,     # Provider (avoiding import)
    expiry: date | None = None,
) -> OptionChain:
    """Parse raw broker option chain response into an OptionChain.

    Handles the common pattern shared by Dhan and Upstox:
    - Iterate strike data from "strikes" or "data" keys
    - Extract call/put legs (supporting both "call"/"put" and "CE"/"PE" keys)
    - Build OptionContract with full Instrument for each leg

    Args:
        raw_data: Raw broker response (dict or list)
        underlying: The underlying Instrument object
        provider: The provider that created the instruments
        expiry: Expected expiry date (used as fallback)

    Returns:
        OptionChain with parsed contracts
    """
    from brokers.domain.instrument import Instrument

    contracts: list[OptionContract] = []

    if isinstance(raw_data, dict):
        strike_data_list = raw_data.get("strikes", raw_data.get("data", []))
        if not isinstance(strike_data_list, list):
            strike_data_list = []

        for strike_data in strike_data_list:
            if not isinstance(strike_data, dict):
                continue

            strike_val = Decimal(str(strike_data.get("strike", strike_data.get("strikePrice", 0))))
            exp_date = expiry or date.today()

            # Call leg
            call_data = strike_data.get("call", strike_data.get("CE", {}))
            if call_data:
                sym = str(call_data.get("symbol", call_data.get("tradingSymbol", "")))
                contracts.append(OptionContract(
                    instrument=Instrument(
                        symbol=sym,
                        exchange=underlying.exchange,
                        asset_class=AssetClass.OPTION,
                        provider=provider,
                        expiry=exp_date,
                        strike=strike_val,
                        option_type=OptionType.CALL,
                    ),
                    strike=strike_val,
                    option_type=OptionType.CALL,
                    expiry=exp_date,
                    ltp=_dec_optional(call_data.get("ltp")),
                    oi=int(call_data.get("oi", 0)) if call_data.get("oi") else None,
                    volume=int(call_data.get("volume", 0)) if call_data.get("volume") else None,
                ))

            # Put leg
            put_data = strike_data.get("put", strike_data.get("PE", {}))
            if put_data:
                sym = str(put_data.get("symbol", put_data.get("tradingSymbol", "")))
                contracts.append(OptionContract(
                    instrument=Instrument(
                        symbol=sym,
                        exchange=underlying.exchange,
                        asset_class=AssetClass.OPTION,
                        provider=provider,
                        expiry=exp_date,
                        strike=strike_val,
                        option_type=OptionType.PUT,
                    ),
                    strike=strike_val,
                    option_type=OptionType.PUT,
                    expiry=exp_date,
                    ltp=_dec_optional(put_data.get("ltp")),
                    oi=int(put_data.get("oi", 0)) if put_data.get("oi") else None,
                    volume=int(put_data.get("volume", 0)) if put_data.get("volume") else None,
                ))

    # Extract spot price
    spot_raw = raw_data.get("spot", raw_data.get("underlyingValue")) if isinstance(raw_data, dict) else None
    spot = Decimal(str(spot_raw)) if spot_raw else None

    return OptionChain(
        underlying=underlying,
        contracts=contracts,
        spot=spot,
    )


def _dec_optional(val: Any) -> Decimal | None:
    """Parse a value to Decimal, returning None for missing values."""
    if val is None or val == "":
        return None
    try:
        return Decimal(str(val))
    except (ValueError, TypeError):
        return None


__all__ = ["parse_option_chain"]
