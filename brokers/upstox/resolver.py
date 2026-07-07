"""Upstox instrument resolver — maps canonical symbols to Upstox instrument keys.

Upstox uses composite instrument_keys (e.g. "NSE_EQ|INE002A01018") for all API calls.
This resolver loads instrument master data from Upstox's JSON file and provides
O(1) lookup by symbol, trading symbol, or instrument_key.

Usage::

    resolver = UpstoxInstrumentResolver()
    resolver.load_cached()  # Load from cache or download
    inst = resolver.resolve("RELIANCE", Exchange.NSE)
    print(inst.broker_id)  # "NSE_EQ|INE002A01018"
"""

from __future__ import annotations

import gzip
import json
import logging
import os
from pathlib import Path
from typing import Any
from urllib.request import urlopen

from brokers.common.instrument_resolver import (
    InMemoryInstrumentResolver,
    ResolvedInstrument,
)
from brokers.domain.enums import Exchange, InstrumentType
from decimal import Decimal

logger = logging.getLogger(__name__)

# ── Upstox segment mapping ─────────────────────────────────────────────────

_UPSTOX_SEGMENT_TO_EXCHANGE: dict[str, Exchange] = {
    "NSE_EQ": Exchange.NSE,
    "BSE_EQ": Exchange.BSE,
    "NSE_FO": Exchange.NFO,
    "BSE_FO": Exchange.NFO,
    "MCX_FO": Exchange.MCX,
    "NSE_INDEX": Exchange.INDEX,
    "BSE_INDEX": Exchange.INDEX,
    "NSE_COM": Exchange.MCX,
    "BSE_COM": Exchange.MCX,
    "NSE_CURRENCY": Exchange.MCX,
    "BSE_CURRENCY": Exchange.MCX,
}

_EXCHANGE_TO_SEGMENT: dict[str, str] = {
    "NSE": "NSE_EQ",
    "BSE": "BSE_EQ",
    "NFO": "NSE_FO",
    "MCX": "MCX_FO",
    "INDEX": "NSE_INDEX",
}


# ── Upstox instrument resolver ─────────────────────────────────────────────


class UpstoxInstrumentResolver(InMemoryInstrumentResolver):
    """Upstox-specific instrument resolver.

    Loads instruments from Upstox's complete.json.gz master file and maps
    them to ResolvedInstrument objects with composite instrument_keys.
    """

    # Upstox instrument master URL
    INSTRUMENTS_URL = "https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz"

    # Cache directory
    DEFAULT_CACHE_DIR = ".cache/upstox"

    def __init__(self) -> None:
        super().__init__(broker_name="upstox")

    # ── Loading ──────────────────────────────────────────────────────────

    def load_from_rows(self, rows: list[dict[str, Any]]) -> dict[str, int]:
        """Load instruments from a list of JSON dict rows.

        Returns stats dict with 'total', 'registered', 'skipped' counts.
        """
        instruments: list[ResolvedInstrument] = []
        skipped = 0

        for row in rows:
            try:
                inst = self._row_to_instrument(row)
                if inst is not None:
                    instruments.append(inst)
                else:
                    skipped += 1
            except Exception as exc:
                skipped += 1
                logger.debug("upstox_row_parse_failed", extra={"error": str(exc)[:100]})

        registered = self.register_many(instruments)

        stats = {
            "total": len(rows),
            "registered": registered,
            "skipped": skipped,
        }
        logger.info("upstox_instruments_loaded", extra=stats)
        return stats

    def load_from_file(self, path: str | Path) -> dict[str, int]:
        """Load instruments from a local JSON or JSON.gz file."""
        path = Path(path)
        if path.suffix == ".gz":
            with gzip.open(path, "rt", encoding="utf-8") as f:
                data = json.load(f)
        else:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)

        # Upstox file is a list of instrument dicts
        if isinstance(data, dict) and "data" in data:
            data = data["data"]
        if not isinstance(data, list):
            data = [data]
        return self.load_from_rows(data)

    def load_from_url(self, url: str) -> dict[str, int]:
        """Download and load instruments from a URL."""
        with urlopen(url) as resp:
            raw = resp.read()
        # Handle gzip
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        data = json.loads(raw.decode("utf-8"))
        if isinstance(data, dict) and "data" in data:
            data = data["data"]
        if not isinstance(data, list):
            data = [data]
        return self.load_from_rows(data)

    def load_cached(self, force_refresh: bool = False) -> dict[str, int]:
        """Load from cache, downloading if stale or missing.

        Cache TTL: 24 hours (verified from archive).
        """
        cache_dir = Path(os.environ.get("UPSTOX_CACHE_DIR", self.DEFAULT_CACHE_DIR))
        cache_file = cache_dir / "complete.json.gz"
        parsed_cache = cache_dir / "complete_parsed.json.gz"

        # Try parsed cache first (faster)
        if not force_refresh and parsed_cache.exists():
            age = _file_age_hours(parsed_cache)
            if age < 24:
                try:
                    return self.load_from_file(parsed_cache)
                except Exception as exc:
                    logger.warning("upstox_parsed_cache_load_failed", extra={"error": str(exc)[:100]})

        # Try raw cache
        if not force_refresh and cache_file.exists():
            age = _file_age_hours(cache_file)
            if age < 24:
                try:
                    return self.load_from_file(cache_file)
                except Exception as exc:
                    logger.warning("upstox_raw_cache_load_failed", extra={"error": str(exc)[:100]})

        # Download fresh
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            with urlopen(self.INSTRUMENTS_URL) as resp:
                raw = resp.read()
            cache_file.write_bytes(raw)
            logger.info("upstox_downloaded", extra={"size_bytes": len(raw)})

            # Parse and save parsed cache
            decompressed = gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw
            data = json.loads(decompressed.decode("utf-8"))
            if isinstance(data, dict) and "data" in data:
                data = data["data"]
            if not isinstance(data, list):
                data = [data]

            # Save parsed cache as gzip JSON
            with gzip.open(parsed_cache, "wt", encoding="utf-8") as f:
                json.dump(data, f)

            return self.load_from_rows(data)
        except Exception as exc:
            logger.error("upstox_download_failed", extra={"error": str(exc)[:200]})
            # Fallback to any existing cache
            if cache_file.exists():
                logger.warning("upstox_using_stale_cache", extra={"path": str(cache_file)})
                return self.load_from_file(cache_file)
            raise

    # ── Row parsing ──────────────────────────────────────────────────────

    def _row_to_instrument(self, row: dict[str, Any]) -> ResolvedInstrument | None:
        """Parse a JSON row into a ResolvedInstrument."""
        instrument_key = str(row.get("instrument_key", "")).strip()
        if not instrument_key:
            return None

        # Upstox instrument_key format: "SEGMENT|IDENTIFIER" (e.g. "NSE_EQ|INE002A01018")
        parts = instrument_key.split("|", 1)
        segment = parts[0] if len(parts) > 0 else ""
        parts[1] if len(parts) > 0 else ""

        # Map segment to Exchange
        exchange = _UPSTOX_SEGMENT_TO_EXCHANGE.get(segment, Exchange.NSE)

        # Trading symbol and canonical symbol
        trading_symbol = str(row.get("trading_symbol", row.get("tradingSymbol", ""))).strip()
        name = str(row.get("name", row.get("symbol", ""))).strip()

        # Use name as canonical symbol (for equities this is the clean symbol like "RELIANCE")
        # For derivatives, use the underlying
        instrument_type_str = str(row.get("instrument_type", row.get("instrumentType", ""))).strip().upper()

        # Map instrument type
        if segment.endswith("_INDEX"):
            instrument_type = InstrumentType.INDEX
        elif instrument_type_str in ("EQUITY", "STOCK", ""):
            instrument_type = InstrumentType.EQUITY
        elif instrument_type_str in ("OPTION", "OPTSTK", "OPTIDX"):
            instrument_type = InstrumentType.OPTIONS
        elif instrument_type_str in ("FUTURE", "FUTSTK", "FUTIDX"):
            instrument_type = InstrumentType.FUTURES
        elif instrument_type_str in ("COMMODITY",):
            instrument_type = InstrumentType.COMMODITY
        elif instrument_type_str in ("CURRENCY",):
            instrument_type = InstrumentType.CURRENCY
        else:
            instrument_type = InstrumentType.EQUITY

        # Determine canonical symbol
        if instrument_type == InstrumentType.EQUITY:
            canonical = name or trading_symbol
        elif instrument_type == InstrumentType.INDEX:
            canonical = name or trading_symbol
        else:
            # For derivatives, use underlying
            underlying = str(row.get("underlying_symbol", row.get("underlyingSymbol", ""))).strip()
            canonical = underlying or name or trading_symbol

        # Parse lot size, tick size, expiry, strike
        lot_size = _safe_int(row.get("lot_size", row.get("lotSize")), 1)
        tick_size = _safe_decimal(row.get("tick_size", row.get("tickSize")), Decimal("0.05")) or Decimal("0.05")
        expiry = str(row.get("expiry", row.get("expiryDate", ""))).strip() or None
        strike = _safe_decimal(row.get("strike_price", row.get("strikePrice", row.get("strike"))), None)
        isin = str(row.get("isin", "")).strip()

        return ResolvedInstrument(
            symbol=canonical,
            exchange=exchange,
            broker_id=instrument_key,
            segment=segment,
            instrument_type=instrument_type,
            lot_size=lot_size,
            tick_size=tick_size,
            trading_symbol=trading_symbol,
            expiry=expiry,
            strike=strike,
            isin=isin,
            underlying=str(row.get("underlying_symbol", row.get("underlyingSymbol", ""))).strip(),
        )

    # ── Alternate key generation (Upstox-specific) ───────────────────────

    def _generate_alternate_keys(self, inst: ResolvedInstrument) -> list[str]:
        """Generate Upstox-specific alternate lookup keys."""
        keys = super()._generate_alternate_keys(inst)

        # Upstox-specific: add ISIN as an alternate key for broker_id lookup
        if inst.isin:
            keys.append(inst.isin)

        # Add identifier portion of instrument_key for broker_id lookup
        parts = inst.broker_id.split("|", 1)
        if len(parts) > 1:
            keys.append(parts[1])

        return keys


# ── Helpers ────────────────────────────────────────────────────────────────


def _safe_int(val: Any, default: int = 0) -> int:
    if val is None or val == "":
        return default
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default


def _safe_decimal(val: Any, default: Decimal | None) -> Decimal | None:
    if val is None or val == "":
        return default
    try:
        return Decimal(str(val))
    except (ValueError, TypeError):
        return default


def _file_age_hours(path: Path) -> float:
    """Return age of file in hours."""
    import time
    mtime = path.stat().st_mtime
    return (time.time() - mtime) / 3600


__all__ = ["UpstoxInstrumentResolver"]
