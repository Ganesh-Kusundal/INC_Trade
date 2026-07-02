"""Upstox instrument search via ``/v2/instrument/search``."""

from __future__ import annotations

from typing import Any

from .definition import UpstoxInstrumentDefinition


class UpstoxInstrumentSearch:
    def __init__(self, http_client: Any) -> None:
        self._http = http_client

    def search(
        self,
        symbol: str,
        exchange_segment: str | None = None,
    ) -> list[UpstoxInstrumentDefinition]:
        from .loader import UpstoxInstrumentLoader
        from .segment_mapper import UpstoxSegmentMapper

        url = (
            self._http.url_resolver.instrument_search_url()
            if hasattr(self._http, "url_resolver")
            else None
        )
        if url is None:
            from brokers.upstox.auth.urls import UpstoxApiUrlResolver

            resolver = UpstoxApiUrlResolver(self._http.settings)
            url = resolver.instrument_search_url()

        params: dict[str, str] = {"symbol": symbol}
        if exchange_segment:
            params["segment"] = UpstoxSegmentMapper.to_wire(exchange_segment)
        body = self._http.get_json(url, params=params)
        rows = body.get("data") if isinstance(body, dict) else body
        if not isinstance(rows, list):
            return []
        UpstoxInstrumentLoader()
        out: list[UpstoxInstrumentDefinition] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                out.append(
                    UpstoxInstrumentDefinition(
                        instrument_key=row.get("instrument_key", ""),
                        exchange=row.get("exchange", ""),
                        exchange_segment=row.get("segment", ""),
                        instrument_type=row.get("instrument_type", ""),
                        symbol=row.get("symbol", ""),
                        trading_symbol=row.get("trading_symbol", row.get("symbol", "")),
                        name=row.get("name", ""),
                        isin=row.get("isin", ""),
                        lot_size=int(row.get("lot_size", 0) or 0),
                        tick_size=float(row.get("tick_size", 0) or 0.0),
                        expiry=row.get("expiry"),
                        strike=_to_float(row.get("strike")),
                        option_type=row.get("option_type"),
                        underlying_key=row.get("underlying_key") or row.get("underlying_symbol"),
                        freeze_qty=_to_int(row.get("freeze_qty")),
                    )
                )
            except Exception:
                continue
        return out


def _to_float(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value):
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
