"""Options and futures chain domain entities."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from domain.parsing import parse_decimal as _decimal_or_none
from domain.parsing import parse_int as _parse_int_or_none


@dataclass(slots=True, frozen=True)
class OptionContract:
    """Option chain contract with greeks and market data.

    Frozen for immutability — all fields are value types.
    """

    strike: Decimal = Decimal("0")
    expiry: str = ""
    instrument_type: str = "OPTION"
    exchange: str = "NFO"
    lot_size: int = 0
    call_ltp: Decimal | None = None
    call_bid: Decimal | None = None
    call_ask: Decimal | None = None
    call_iv: Decimal | None = None
    call_oi: int | None = None
    call_volume: int | None = None
    put_ltp: Decimal | None = None
    put_bid: Decimal | None = None
    put_ask: Decimal | None = None
    put_iv: Decimal | None = None
    put_oi: int | None = None
    put_volume: int | None = None


@dataclass(slots=True, frozen=True)
class OptionLeg:
    """Single CE or PE leg within an option chain strike row."""

    ltp: Decimal | None = None
    oi: int | None = None
    volume: int | None = None
    iv: Decimal | None = None
    bid: Decimal | None = None
    ask: Decimal | None = None
    symbol: str | None = None
    instrument_key: str | None = None
    trading_symbol: str | None = None
    instrument_id: str | None = None
    greeks: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, data: dict | None) -> OptionLeg:
        if not isinstance(data, dict):
            return cls()
        # Greeks may arrive nested under "greeks" or as flat top-level keys
        # (the Dhan adapter outputs delta/theta/gamma/vega inline).
        nested_greeks = data.get("greeks")
        if isinstance(nested_greeks, dict) and nested_greeks:
            greeks = dict(nested_greeks)
        else:
            flat = {}
            for key in ("delta", "theta", "gamma", "vega", "rho"):
                val = data.get(key)
                if val is not None:
                    flat[key] = val
            greeks = flat or None
        return cls(
            ltp=_decimal_or_none(data.get("ltp")),
            oi=_parse_int_or_none(data.get("oi")),
            volume=_parse_int_or_none(data.get("volume")),
            iv=_decimal_or_none(data.get("iv")),
            bid=_decimal_or_none(data.get("bid")),
            ask=_decimal_or_none(data.get("ask")),
            symbol=data.get("symbol"),
            instrument_key=data.get("instrument_key") or data.get("security_id"),
            trading_symbol=data.get("trading_symbol") or data.get("tradingSymbol"),
            greeks=greeks,
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "ltp": self.ltp,
            "oi": self.oi,
            "volume": self.volume,
            "iv": self.iv,
            "bid": self.bid,
            "ask": self.ask,
            "symbol": self.symbol,
            "instrument_key": self.instrument_key,
            "trading_symbol": self.trading_symbol,
        }
        if self.greeks:
            out["greeks"] = self.greeks
        return out


@dataclass(slots=True, frozen=True)
class OptionStrike:
    """One strike row with call and put legs."""

    strike: Decimal
    call: OptionLeg = field(default_factory=OptionLeg)
    put: OptionLeg = field(default_factory=OptionLeg)

    @classmethod
    def from_dict(cls, data: dict) -> OptionStrike:
        strike_val = data.get("strike") or data.get("strikePrice")
        strike = _decimal_or_none(strike_val) or Decimal("0")
        call_raw = data.get("call") or data.get("CE") or {}
        put_raw = data.get("put") or data.get("PE") or {}
        return cls(
            strike=strike,
            call=OptionLeg.from_dict(call_raw if isinstance(call_raw, dict) else {}),
            put=OptionLeg.from_dict(put_raw if isinstance(put_raw, dict) else {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "strike": self.strike,
            "call": self.call.to_dict(),
            "put": self.put.to_dict(),
        }


@dataclass(slots=True, frozen=True)
class OptionChain:
    """Canonical option chain returned by :class:`~brokers.common.gateway.MarketDataGateway`."""

    underlying: str
    exchange: str
    expiry: str
    strikes: tuple[OptionStrike, ...] = ()
    spot: Decimal | None = None

    @classmethod
    def from_dict(cls, data: dict | None) -> OptionChain:
        if not data:
            return cls(underlying="", exchange="", expiry="")
        strikes = tuple(
            OptionStrike.from_dict(row) for row in data.get("strikes", []) if isinstance(row, dict)
        )
        return cls(
            underlying=str(data.get("underlying", "")),
            exchange=str(data.get("exchange", "")),
            expiry=str(data.get("expiry", "")),
            strikes=strikes,
            spot=_decimal_or_none(data.get("spot")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "underlying": self.underlying,
            "exchange": self.exchange,
            "expiry": self.expiry,
            "strikes": [row.to_dict() for row in self.strikes],
            "spot": self.spot,
        }


@dataclass(slots=True, frozen=True)
class FutureContract:
    """Single futures contract within a chain."""

    symbol: str = ""
    expiry: str = ""
    ltp: Decimal | None = None
    oi: int | None = None
    lot_size: int = 1
    underlying: str = ""
    instrument_id: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> FutureContract:
        return cls(
            symbol=str(data.get("symbol", "")),
            expiry=str(data.get("expiry", "")),
            ltp=_decimal_or_none(data.get("ltp")),
            oi=_parse_int_or_none(data.get("oi")),
            lot_size=int(data.get("lot_size", 1) or 1),
            underlying=str(data.get("underlying", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "expiry": self.expiry,
            "ltp": self.ltp,
            "oi": self.oi,
            "lot_size": self.lot_size,
            "underlying": self.underlying,
        }


@dataclass(slots=True, frozen=True)
class FutureChain:
    """Canonical futures chain returned by :class:`~brokers.common.gateway.MarketDataGateway`."""

    underlying: str
    exchange: str
    expiries: tuple[str, ...] = ()
    contracts: tuple[FutureContract, ...] = ()

    @classmethod
    def from_dict(cls, data: dict | None) -> FutureChain:
        if not data:
            return cls(underlying="", exchange="")
        contracts = tuple(
            FutureContract.from_dict(row)
            for row in data.get("contracts", [])
            if isinstance(row, dict)
        )
        expiries_raw = data.get("expiries", [])
        expiries = tuple(str(e) for e in expiries_raw) if isinstance(expiries_raw, list) else ()
        return cls(
            underlying=str(data.get("underlying", "")),
            exchange=str(data.get("exchange", "")),
            expiries=expiries,
            contracts=contracts,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "underlying": self.underlying,
            "exchange": self.exchange,
            "expiries": list(self.expiries),
            "contracts": [c.to_dict() for c in self.contracts],
        }
