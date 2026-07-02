"""Canonical Instrument Registry — hides broker-specific IDs from consumers.

Consumers use symbol names like "NIFTY", "RELIANCE" — never security_id or instrument_key.
The registry translates between canonical names and broker-specific identifiers.

Usage:
    from brokers.common.services.instrument_registry import CanonicalInstrumentRegistry

    registry = CanonicalInstrumentRegistry(gateway)

    # Resolve by name
    inst = registry.resolve("RELIANCE", exchange="NFO")

    # Get ATM option
    atm = registry.atm("NIFTY", spot_price=24500)

    # Get current future
    future = registry.current_future("NIFTY")

    # Get option chain by name (not by security_id)
    chain = registry.option_chain("NIFTY", expiry="2026-07-30")

    # Search
    results = registry.search("RELIANCE")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from domain import OptionChain
from domain.symbols import normalize_exchange, normalize_symbol

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CanonicalInstrument:
    """Broker-agnostic instrument representation.

    Consumers see this — never security_id or instrument_key.
    """

    symbol: str
    exchange: str
    name: str = ""
    instrument_type: str = ""  # EQUITY, FUTURE, OPTION, INDEX
    option_type: str = ""  # CE, PE, or empty
    strike_price: float = 0.0
    expiry: str = ""
    underlying: str = ""
    lot_size: int = 1
    tick_size: float = 0.05

    # Internal broker mapping (NOT exposed to consumers via API)
    _broker_id: str = field(default="", repr=False)
    _broker_exchange: str = field(default="", repr=False)

    @property
    def is_option(self) -> bool:
        return self.instrument_type == "OPTION"

    @property
    def is_future(self) -> bool:
        return self.instrument_type == "FUTURE"

    @property
    def is_equity(self) -> bool:
        return self.instrument_type in ("EQUITY", "")

    @property
    def canonical_symbol(self) -> str:
        """Human-readable canonical symbol."""
        if self.is_option:
            return f"{self.underlying} {self.expiry} {self.strike_price:.0f} {self.option_type}"
        if self.is_future:
            return f"{self.underlying} {self.expiry} FUT"
        return self.symbol


@dataclass
class CanonicalInstrumentRegistry:
    """Canonical instrument registry that hides broker-specific IDs.

    Wraps any gateway and provides broker-agnostic instrument resolution.
    """

    def __init__(self, gateway: Any) -> None:
        self._gateway = gateway
        self._cache: dict[tuple[str, str], CanonicalInstrument] = {}
        self._loaded = False

    def _ensure_loaded(self) -> None:
        """Load instruments if not already loaded."""
        if not self._loaded:
            try:
                self._gateway.load_instruments()
                self._loaded = True
            except Exception as exc:
                logger.warning("Failed to load instruments: %s", exc)

    def resolve(self, symbol: str, exchange: str = "NSE") -> CanonicalInstrument | None:
        """Resolve a symbol to a canonical instrument.

        Parameters
        ----------
        symbol : str
            Trading symbol (e.g., "RELIANCE", "NIFTY", "NIFTY 26 JUN 25000 CE").
        exchange : str
            Exchange (NSE, BSE, NFO, etc.).

        Returns
        -------
        CanonicalInstrument or None if not found.
        """
        self._ensure_loaded()
        key = (normalize_symbol(symbol), normalize_exchange(exchange))
        if key in self._cache:
            return self._cache[key]

        # Try gateway search
        results = self._gateway.search(symbol) if hasattr(self._gateway, "search") else []
        for r in results:
            if r.get("symbol", "").upper() == symbol.upper():
                inst = self._to_canonical(r, exchange)
                self._cache[key] = inst
                return inst

        # If single result, use it
        if len(results) == 1:
            inst = self._to_canonical(results[0], exchange)
            self._cache[key] = inst
            return inst

        return None

    def resolve_required(self, symbol: str, exchange: str = "NSE") -> CanonicalInstrument:
        """Resolve a symbol, raising ValueError if not found."""
        inst = self.resolve(symbol, exchange)
        if inst is None:
            raise ValueError(f"Instrument not found: {symbol} ({exchange})")
        return inst

    def atm(
        self,
        underlying: str,
        spot_price: float,
        exchange: str = "NFO",
        expiry: str | None = None,
    ) -> dict[str, CanonicalInstrument | None]:
        """Get ATM call and put for the given underlying and spot price.

        Parameters
        ----------
        underlying : str
            Underlying symbol (e.g., "NIFTY").
        spot_price : float
            Current spot price to compute ATM strike.
        exchange : str
            Exchange (default NFO).
        expiry : str or None
            Expiry date. If None, uses nearest expiry.

        Returns
        -------
        Dict with "call" and "put" keys, each a CanonicalInstrument or None.
        """
        self._ensure_loaded()

        # Get option chain
        chain = (
            self._gateway.option_chain(underlying, exchange=exchange, expiry=expiry)
            if hasattr(self._gateway, "option_chain")
            else {}
        )

        strikes = chain.get("strikes", [])
        if not strikes:
            return {"call": None, "put": None}

        # Find ATM strike (closest to spot)
        strike_values = [s.get("strike", 0) for s in strikes]
        atm_strike = min(strike_values, key=lambda x: abs(x - spot_price)) if strike_values else 0

        # Find CE and PE at ATM strike
        call_inst = None
        put_inst = None
        for s in strikes:
            if s.get("strike") == atm_strike:
                opt_type = (s.get("option_type") or "").upper()
                has_call = (
                    opt_type in ("CALL", "CE")
                    or s.get("call_ltp") is not None
                    or s.get("ce_ltp") is not None
                )
                has_put = (
                    opt_type in ("PUT", "PE")
                    or s.get("put_ltp") is not None
                    or s.get("pe_ltp") is not None
                )
                if has_call and call_inst is None:
                    call_inst = CanonicalInstrument(
                        symbol=f"{underlying} {atm_strike:.0f} CALL",
                        exchange=exchange,
                        name=f"{underlying} ATM Call",
                        instrument_type="OPTION",
                        option_type="CALL",
                        strike_price=atm_strike,
                        expiry=expiry or chain.get("expiry", ""),
                        underlying=underlying,
                    )
                if has_put and put_inst is None:
                    put_inst = CanonicalInstrument(
                        symbol=f"{underlying} {atm_strike:.0f} PUT",
                        exchange=exchange,
                        name=f"{underlying} ATM Put",
                        instrument_type="OPTION",
                        option_type="PUT",
                        strike_price=atm_strike,
                        expiry=expiry or chain.get("expiry", ""),
                        underlying=underlying,
                    )
                if call_inst is not None and put_inst is not None:
                    break

        return {"call": call_inst, "put": put_inst}

    def current_future(
        self,
        underlying: str,
        exchange: str = "NFO",
    ) -> CanonicalInstrument | None:
        """Get the current (nearest expiry) future for an underlying.

        Parameters
        ----------
        underlying : str
            Underlying symbol (e.g., "NIFTY", "RELIANCE").
        exchange : str
            Exchange (default NFO).

        Returns
        -------
        CanonicalInstrument for the nearest future, or None.
        """
        self._ensure_loaded()

        chain = (
            self._gateway.future_chain(underlying, exchange=exchange)
            if hasattr(self._gateway, "future_chain")
            else {}
        )

        contracts = chain.get("contracts", [])
        if not contracts:
            return None

        # Nearest expiry
        nearest = min(contracts, key=lambda c: c.get("expiry", "9999"))
        return CanonicalInstrument(
            symbol=f"{underlying} {nearest.get('expiry', '')} FUT",
            exchange=exchange,
            name=f"{underlying} Near Month Future",
            instrument_type="FUTURE",
            expiry=nearest.get("expiry", ""),
            underlying=underlying,
        )

    def option_chain(
        self,
        underlying: str,
        exchange: str = "NFO",
        expiry: str | None = None,
    ) -> list[dict]:
        """Get option chain as list of canonical strike dicts.

        Returns list of dicts with: strike, expiry, call_ltp, put_ltp, call_oi, put_oi.
        No security_id exposed.
        """
        self._ensure_loaded()

        chain = (
            self._gateway.option_chain(underlying, exchange=exchange, expiry=expiry)
            if hasattr(self._gateway, "option_chain")
            else OptionChain(underlying="", exchange="", expiry="")
        )

        if hasattr(chain, "strikes"):
            return [row.to_dict() for row in chain.strikes]
        if isinstance(chain, dict):
            return chain.get("strikes", [])
        return []

    def future_chain(
        self,
        underlying: str,
        exchange: str = "NFO",
    ) -> list[dict]:
        """Get futures chain as list of canonical contract dicts.

        Returns list of dicts with: expiry, ltp, volume, oi, change.
        No security_id exposed.
        """
        self._ensure_loaded()

        chain = (
            self._gateway.future_chain(underlying, exchange=exchange)
            if hasattr(self._gateway, "future_chain")
            else None
        )

        if chain is not None and hasattr(chain, "contracts"):
            return [c.to_dict() for c in chain.contracts]
        if isinstance(chain, dict):
            return chain.get("contracts", [])
        return []

    def search(self, query: str, exchange: str | None = None) -> list[CanonicalInstrument]:
        """Search instruments by symbol prefix.

        Returns list of CanonicalInstrument — no security_id exposed.
        """
        self._ensure_loaded()

        results = self._gateway.search(query) if hasattr(self._gateway, "search") else []
        instruments = []
        for r in results:
            if exchange and normalize_exchange(r.get("exchange", "")) != normalize_exchange(exchange):
                continue
            instruments.append(self._to_canonical(r, exchange or r.get("exchange", "NSE")))
        return instruments

    def _to_canonical(self, raw: dict, default_exchange: str = "NSE") -> CanonicalInstrument:
        """Convert a raw instrument dict to CanonicalInstrument."""
        return CanonicalInstrument(
            symbol=raw.get("symbol", ""),
            exchange=raw.get("exchange", default_exchange),
            name=raw.get("name", raw.get("canonical_symbol", "")),
            instrument_type=raw.get("type", raw.get("instrument_type", "")),
            option_type=raw.get("option_type", ""),
            strike_price=float(raw.get("strike_price", 0)),
            expiry=raw.get("expiry", ""),
            underlying=raw.get("underlying", ""),
            lot_size=int(raw.get("lot_size", 1)),
            tick_size=float(raw.get("tick_size", 0.05)),
            _broker_id=str(raw.get("security_id", raw.get("instrument_key", ""))),
            _broker_exchange=raw.get("exchange", default_exchange),
        )
