"""Upstox instrument definition record."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class UpstoxInstrumentDefinition:
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

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UpstoxInstrumentDefinition:
        return cls(
            instrument_key=str(data.get("instrument_key", "")),
            exchange=str(data.get("exchange", "")),
            exchange_segment=str(data.get("segment", data.get("exchange_segment", ""))),
            instrument_type=str(data.get("instrument_type", "")),
            symbol=str(data.get("symbol", data.get("trading_symbol", ""))),
            trading_symbol=str(data.get("trading_symbol", data.get("symbol", ""))),
            name=str(data.get("name", "")),
            isin=str(data.get("isin", "")),
            lot_size=int(data.get("lot_size", 0) or 0),
            tick_size=float(data.get("tick_size", 0) or 0),
            expiry=data.get("expiry"),
            strike=data.get("strike"),
            option_type=data.get("option_type"),
            underlying_key=data.get("underlying_key"),
            underlying_symbol=data.get("underlying_symbol"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "instrument_key": self.instrument_key,
            "exchange": self.exchange,
            "exchange_segment": self.exchange_segment,
            "instrument_type": self.instrument_type,
            "symbol": self.symbol,
            "trading_symbol": self.trading_symbol,
            "name": self.name,
            "isin": self.isin,
            "lot_size": self.lot_size,
            "tick_size": self.tick_size,
            "expiry": self.expiry,
            "strike": self.strike,
            "option_type": self.option_type,
            "underlying_key": self.underlying_key,
            "underlying_symbol": self.underlying_symbol,
        }
