"""Pydantic definition of an Upstox instrument record.

Mirrors Trade_J ``UpstoxInstrumentDefinition``.
"""

from __future__ import annotations

from pydantic import BaseModel


class UpstoxInstrumentDefinition(BaseModel):
    instrument_key: str = ""
    exchange: str = ""
    exchange_segment: str = ""
    instrument_type: str = ""
    symbol: str = ""
    trading_symbol: str = ""
    name: str = ""
    isin: str = ""
    lot_size: int = 0
    tick_size: float = 0.0
    expiry: str | None = None
    strike: float | None = None
    option_type: str | None = None
    underlying_key: str | None = None
    underlying_symbol: str | None = None
    freeze_qty: int | None = None
    minimum_lot: int | None = None
    short_name: str | None = None
    company_name: str | None = None

    @property
    def is_option(self) -> bool:
        return self.instrument_type.upper() in ("OPTION", "OPT", "CE", "PE")

    @property
    def is_future(self) -> bool:
        return self.instrument_type.upper() in ("FUTURE", "FUT")

    @property
    def is_equity(self) -> bool:
        return self.instrument_type.upper() in ("EQUITY", "EQ")

    @property
    def is_index(self) -> bool:
        return self.instrument_type.upper() in ("INDEX", "IDX")
