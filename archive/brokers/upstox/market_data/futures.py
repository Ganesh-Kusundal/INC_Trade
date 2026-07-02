"""Upstox futures client — live contracts from instrument master.

Expired-instrument APIs are retained for historical/backtest lookups only.
Live ``future_chain`` reads active FUT definitions from the loaded instrument
master via :class:`~brokers.upstox.instruments.resolver.UpstoxInstrumentResolver`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from brokers.upstox.auth.urls import UpstoxApiUrlResolver

if TYPE_CHECKING:
    from brokers.upstox.instruments.resolver import UpstoxInstrumentResolver


class UpstoxFuturesClient:
    def __init__(
        self,
        http_client: Any,
        url_resolver: UpstoxApiUrlResolver,
        instrument_resolver: UpstoxInstrumentResolver | None = None,
    ) -> None:
        self._http = http_client
        self._urls = url_resolver
        self._resolver = instrument_resolver

    def _resolve_underlying_key(self, underlying: str, exchange_segment: str) -> str:
        from indices import index_upstox_key, upstox_index_segment

        idx_key = index_upstox_key(underlying)
        if idx_key is not None:
            return idx_key
        if self._resolver is not None:
            seg = exchange_segment
            if underlying.upper() in {
                "NIFTY",
                "BANKNIFTY",
                "FINNIFTY",
                "MIDCPNIFTY",
                "SENSEX",
                "BANKEX",
            }:
                normalized = upstox_index_segment(underlying)
                if normalized:
                    seg = normalized
            defn = self._resolver.resolve(symbol=underlying, exchange_segment=seg)
            if defn is not None and defn.instrument_key:
                return defn.instrument_key
        return underlying

    def get_contracts(self, underlying: str, exchange_segment: str = "NFO") -> list[dict[str, Any]]:
        """Return active future contracts for *underlying* from instrument master."""
        if self._resolver is None:
            raise RuntimeError("Upstox instruments not loaded; cannot list live future contracts")
        rows: list[dict[str, Any]] = []
        for defn in self._resolver.list_future_contracts(underlying):
            rows.append(
                {
                    "instrument_key": defn.instrument_key,
                    "symbol": defn.trading_symbol or defn.symbol,
                    "trading_symbol": defn.trading_symbol or defn.symbol,
                    "expiry": (defn.expiry or "")[:10],
                    "lot_size": defn.lot_size or defn.minimum_lot or 1,
                    "underlying": defn.underlying_symbol or underlying,
                    "exchange_segment": defn.exchange_segment,
                }
            )
        if rows:
            return rows
        # Fallback: expired API with resolved instrument_key (historical contracts)
        key = self._resolve_underlying_key(underlying, exchange_segment)
        body = self._http.get_json(
            self._urls.expired_future_contracts_url(),
            params={"instrument_key": key},
        )
        return _data_list(body)

    def get_nearest_contract(
        self, underlying: str, exchange_segment: str = "NFO"
    ) -> dict[str, Any]:
        contracts = self.get_contracts(underlying, exchange_segment)
        return contracts[0] if contracts else {}

    def get_expiries(self, underlying: str, exchange_segment: str = "NFO") -> list[str]:
        if self._resolver is not None:
            try:
                exps = self._resolver.list_future_expiries(underlying)
                if exps:
                    return exps
            except RuntimeError:
                pass
        key = self._resolve_underlying_key(underlying, exchange_segment)
        body = self._http.get_json(
            self._urls.expired_expiries_url(),
            params={"instrument_key": key},
        )
        if isinstance(body, list):
            return [str(x) for x in body]
        data = body.get("data") if isinstance(body, dict) else None
        return [str(x) for x in data] if isinstance(data, list) else []

    def is_commodity(self, underlying: str) -> bool:
        return underlying.upper() in ("GOLD", "SILVER", "CRUDE", "CRUDEOIL", "NATURALGAS")


def _data_list(body: Any) -> list[dict[str, Any]]:
    if not isinstance(body, dict):
        return []
    data = body.get("data")
    return data if isinstance(data, list) else []
