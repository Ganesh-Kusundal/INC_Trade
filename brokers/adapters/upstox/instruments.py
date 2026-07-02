"""Upstox instruments — CSV loader and symbol resolver."""

from __future__ import annotations

import csv
import io
import logging

import requests

from brokers.ports.instruments import InstrumentInfo

logger = logging.getLogger(__name__)

_SEGMENT_URLS = {
    "NSE": "https://api.upstox.com/v2/contracts/MASTER/NSE",
    "BSE": "https://api.upstox.com/v2/contracts/MASTER/BSE",
    "NSE_FO": "https://api.upstox.com/v2/contracts/MASTER/NSE_FO",
    "BSE_FO": "https://api.upstox.com/v2/contracts/MASTER/BSE_FO",
    "MCX_FO": "https://api.upstox.com/v2/contracts/MASTER/MCX_FO",
    "NCD_FO": "https://api.upstox.com/v2/contracts/MASTER/NCD_FO",
}


class UpstoxInstruments:
    def __init__(self) -> None:
        self._instruments: list[InstrumentInfo] = []
        self._by_symbol: dict[str, InstrumentInfo] = {}

    def load(self, segment: str = "NSE") -> None:
        url = _SEGMENT_URLS.get(segment.upper(), _SEGMENT_URLS["NSE"])
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            reader = csv.DictReader(io.StringIO(resp.text))
            for row in reader:
                symbol = row.get("tradingsymbol", row.get("symbol", ""))
                exchange = row.get("exchange", "")
                seg = row.get("segment", "")
                name = row.get("company", row.get("name", ""))
                lot_size = int(row.get("lot_size", 1) or 1)
                info = InstrumentInfo(
                    symbol=symbol.strip(),
                    exchange=exchange.strip(),
                    segment=seg.strip(),
                    name=name.strip(),
                    lot_size=lot_size,
                )
                self._instruments.append(info)
                self._by_symbol[info.symbol.upper()] = info
            logger.info(
                "upstox_instruments_loaded",
                extra={"count": len(self._instruments), "segment": segment},
            )
        except Exception as exc:
            logger.warning("upstox_instruments_load_failed", extra={"error": str(exc)})

    def search(self, query: str, limit: int = 10) -> list[InstrumentInfo]:
        query_upper = query.upper()
        return [i for i in self._instruments if query_upper in i.symbol.upper()][:limit]

    def resolve(self, symbol: str, exchange: str = "NSE") -> InstrumentInfo | None:
        return self._by_symbol.get(symbol.upper())
