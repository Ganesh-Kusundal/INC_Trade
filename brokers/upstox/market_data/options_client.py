"""Upstox options REST client (contracts, chain, greeks, expiries)."""

from __future__ import annotations

from typing import Any

from brokers.upstox.auth.urls import UpstoxApiUrlResolver


class UpstoxOptionsClient:
    def __init__(self, http_client: Any, url_resolver: UpstoxApiUrlResolver) -> None:
        self._http = http_client
        self._urls = url_resolver

    def get_contracts(
        self,
        instrument_key: str,
        expiry: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"instrument_key": instrument_key}
        if expiry:
            params["expiry_date"] = expiry
        return self._http.get_json(self._urls.option_contracts_url(), params=params)

    def get_chain(
        self,
        instrument_key: str,
        expiry: str,
    ) -> dict[str, Any]:
        params = {
            "instrument_key": instrument_key,
            "expiry_date": expiry,
        }
        return self._http.get_json(self._urls.option_chain_url(), params=params)

    def get_expiries(
        self,
        instrument_key: str,
    ) -> list[str]:
        """DEPRECATED: ``/v2/option/expiry`` returns HTTP 400 (see
        ``docs/upstox_verified_capabilities.md``). Expiries are now derived
        from the in-memory instrument master via
        ``UpstoxInstrumentResolver.list_option_expiries``.

        Kept only for backward compatibility; raises to prevent silent
        re-use of the dead endpoint.
        """
        raise NotImplementedError(
            "Upstox /v2/option/expiry is deprecated. Use "
            "UpstoxInstrumentResolver.list_option_expiries(underlying) instead."
        )

    def get_greeks(self, instrument_keys: list[str]) -> dict[str, Any]:
        if isinstance(instrument_keys, str):
            instrument_keys = [instrument_keys]
        params = {"instrument_key": ",".join(instrument_keys)}
        return self._http.get_json(self._urls.option_greeks_url(), params=params)
