"""Upstox options chain adapter."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from brokers.adapters.upstox.http import UpstoxHttpClient
from brokers.adapters.upstox.instruments import resolve_upstox_instrument_key
from brokers.adapters.upstox.instruments import UpstoxInstruments
from brokers.adapters.upstox.urls import resolve_upstox_urls
from brokers.domain.entities import OptionChain, OptionChainEntry

logger = logging.getLogger(__name__)


def _parse_chain_entries(raw: Any) -> tuple[OptionChainEntry, ...]:
    if not isinstance(raw, dict):
        return ()
    entries: list[OptionChainEntry] = []
    for item in raw.get("options", []):
        if isinstance(item, dict):
            entries.append(
                OptionChainEntry(
                    strike_price=Decimal(
                        str(item.get("strike_price", "0") or "0")
                    ),
                    option_type=str(item.get("option_type", "")),
                    last_price=Decimal(
                        str(item.get("last_price", "0") or "0")
                    ),
                    oi=int(item.get("oi", 0) or 0),
                    volume=int(item.get("volume", 0) or 0),
                    raw=item,
                )
            )
    return tuple(entries)


class UpstoxOptions:
    def __init__(
        self,
        client: UpstoxHttpClient,
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
                underlying=underlying, expiry=expiry or "", raw={"chain": {}}
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
            entries=_parse_chain_entries(chain_raw),
            raw=chain_raw if isinstance(chain_raw, dict) else {},
        )
