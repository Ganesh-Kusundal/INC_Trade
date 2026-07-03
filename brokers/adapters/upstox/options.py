"""Upstox options chain adapter."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from brokers.adapters.upstox.instruments import UpstoxInstruments, resolve_upstox_instrument_key
from brokers.adapters.upstox.urls import resolve_upstox_urls
from brokers.domain.entities import OptionChain, OptionLeg, OptionStrike
from brokers.ports.http_client_port import HttpClientPort

logger = logging.getLogger(__name__)


def _parse_chain_entries(raw: Any) -> tuple[OptionStrike, ...]:
    if not isinstance(raw, dict):
        return ()

    # Group by strike price
    by_strike: dict[Decimal, dict[str, dict]] = {}
    for item in raw.get("options", []):
        if not isinstance(item, dict):
            continue
        strike = Decimal(str(item.get("strike_price", "0") or "0"))
        opt_type = str(item.get("option_type", "")).upper()
        if strike not in by_strike:
            by_strike[strike] = {"CE": {}, "PE": {}}
        if opt_type in ("CE", "CALL"):
            by_strike[strike]["CE"] = item
        elif opt_type in ("PE", "PUT"):
            by_strike[strike]["PE"] = item

    strikes: list[OptionStrike] = []
    for strike, legs in sorted(by_strike.items()):
        ce_item = legs["CE"]
        pe_item = legs["PE"]

        ce_leg = OptionLeg(
            ltp=Decimal(str(ce_item.get("last_price", "0") or "0")) if ce_item else None,
            oi=int(ce_item.get("oi", 0) or 0),
            volume=int(ce_item.get("volume", 0) or 0),
            iv=None,
            delta=None,
            theta=None,
            gamma=None,
            vega=None,
            security_id=None,
            symbol=str(ce_item.get("instrument_key", "")),
        )
        pe_leg = OptionLeg(
            ltp=Decimal(str(pe_item.get("last_price", "0") or "0")) if pe_item else None,
            oi=int(pe_item.get("oi", 0) or 0),
            volume=int(pe_item.get("volume", 0) or 0),
            iv=None,
            delta=None,
            theta=None,
            gamma=None,
            vega=None,
            security_id=None,
            symbol=str(pe_item.get("instrument_key", "")),
        )

        strikes.append(OptionStrike(strike=strike, call=ce_leg, put=pe_leg))

    return tuple(strikes)


class UpstoxOptions:
    def __init__(
        self,
        client: HttpClientPort,
        instruments: UpstoxInstruments,
        *,
        environment: str = "LIVE",
    ) -> None:
        self._client = client
        self._instruments = instruments
        self._urls = resolve_upstox_urls(environment)

    def _resolve_underlying_key(self, underlying: str, exchange: str) -> str:
        key = resolve_upstox_instrument_key(underlying, exchange, self._instruments)
        if self._instruments.resolve(underlying, exchange) or key:
            return key
        raise ValueError(
            f"Cannot resolve instrument_key for {underlying!r} on {exchange!r}. "
            "Call gateway.load_instruments() first."
        )

    def get_expiries(self, underlying: str, exchange: str = "NFO") -> list[str]:
        return self._instruments.list_option_expiries(underlying)

    def get_option_chain(
        self,
        underlying: str,
        exchange: str = "NFO",
        expiry: str | None = None,
    ) -> OptionChain:
        instrument_key = self._resolve_underlying_key(underlying, exchange)
        expiries = self.get_expiries(underlying, exchange)
        if not expiries:
            return OptionChain(
                underlying=underlying, expiry=expiry or "", spot=Decimal("0"), strikes=()
            )
        from datetime import date

        today = date.today().isoformat()
        future_expiries = sorted(e for e in expiries if e >= today)
        expiry_date = expiry or (future_expiries[0] if future_expiries else expiries[-1])
        data = self._client.get(
            self._urls.option_chain_url(),
            params={
                "instrument_key": instrument_key,
                "expiry_date": expiry_date,
            },
        )
        chain_raw = data.get("data", data)
        return OptionChain(
            underlying=underlying,
            expiry=expiry_date,
            spot=Decimal("0"),
            strikes=_parse_chain_entries(chain_raw),
        )
