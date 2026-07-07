"""Dhan instrument resolver — maps canonical symbols to Dhan security IDs.

Dhan uses numeric security_ids (e.g. "3456") for all API calls.
This resolver loads instrument master data from Dhan's CSV file and
provides O(1) lookup by symbol, trading symbol, or security_id.

Usage::

    resolver = DhanInstrumentResolver()
    resolver.load_cached()  # Load from cache or download
    inst = resolver.resolve("RELIANCE", Exchange.NSE)
    print(inst.broker_id)  # "3456"
"""

from __future__ import annotations

import csv
import gzip
import io
import logging
import os
from datetime import date, timedelta
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

# ── Dhan CSV column names (verified from archive) ──────────────────────────

_COL_TRADING_SYMBOL = "SEM_TRADING_SYMBOL"
_COL_SECURITY_ID = "SEM_SMST_SECURITY_ID"
_COL_EXCHANGE = "SEM_EXM_EXCH_ID"
_COL_INSTRUMENT_NAME = "SEM_INSTRUMENT_NAME"
_COL_LOT_UNITS = "SEM_LOT_UNITS"
_COL_TICK_SIZE = "SEM_TICK_SIZE"
_COL_EXPIRY = "SEM_EXPIRY_DATE"
_COL_STRIKE = "SEM_STRIKE_PRICE"
_COL_OPTION_TYPE = "SEM_OPTION_TYPE"
_COL_CUSTOM_SYMBOL = "SEM_CUSTOM_SYMBOL"
_COL_UNDERLYING = "SM_SYMBOL_NAME"

# ── Segment to Exchange mapping (verified from archive) ────────────────────

_SEGMENT_TO_EXCHANGE: dict[str, Exchange] = {
    "NSE_EQ": Exchange.NSE,
    "BSE_EQ": Exchange.BSE,
    "NSE_FNO": Exchange.NFO,
    "BSE_FNO": Exchange.NFO,
    "MCX_COMM": Exchange.MCX,
    "NSE_COMM": Exchange.MCX,
    "NSE_CURRENCY": Exchange.MCX,  # Approximate
    "IDX_I": Exchange.INDEX,
}

# Compact CSV segment map (Dhan's compact CSV uses shortened segment codes)
_COMPACT_SEGMENT_MAP: dict[str, str] = {
    "1": "NSE_EQ",
    "2": "NSE_FNO",
    "3": "NSE_CURRENCY",
    "4": "MCX_COMM",
    "5": "BSE_EQ",
    "6": "BSE_FNO",
    "7": "BSE_CURRENCY",
    "0": "IDX_I",
}

# ── Instrument name to type mapping ────────────────────────────────────────

_INSTRUMENT_NAME_TO_TYPE: dict[str, InstrumentType] = {
    "EQUITY": InstrumentType.EQUITY,
    "STOCK": InstrumentType.EQUITY,
    "INDEX": InstrumentType.INDEX,
    "OPTSTK": InstrumentType.OPTIONS,
    "OPTIDX": InstrumentType.OPTIONS,
    "OPTFUT": InstrumentType.OPTIONS,
    "FUTSTK": InstrumentType.FUTURES,
    "FUTIDX": InstrumentType.FUTURES,
    "FUTCOM": InstrumentType.FUTURES,
    "COMMODITY": InstrumentType.COMMODITY,
    "CUR": InstrumentType.CURRENCY,
    "CURFUT": InstrumentType.FUTURES,
    "CUROPT": InstrumentType.OPTIONS,
}


# ── Dhan instrument resolver ───────────────────────────────────────────────


class DhanInstrumentResolver(InMemoryInstrumentResolver):
    """Dhan-specific instrument resolver.

    Loads instruments from Dhan's CSV master file and maps them to
    ResolvedInstrument objects with numeric security_ids.
    """

    # Dhan instrument CSV URL (compact format)
    INSTRUMENT_CSV_URL = "https://images.dhan.co/data/broker-nse/brokerNSEComplete.csv"
    # MCX detailed CSV (for commodity-specific data)
    MCX_CSV_URL = "https://images.dhan.co/data/broker-mcx/brokerMCXComplete.csv"

    # Cache directory (overridable via env)
    DEFAULT_CACHE_DIR = "runtime-dev/instruments"

    def __init__(self) -> None:
        super().__init__(broker_name="dhan")

    # ── Loading ──────────────────────────────────────────────────────────

    def load_from_rows(self, rows: list[dict[str, Any]]) -> dict[str, int]:
        """Load instruments from a list of CSV row dicts.

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
                logger.debug("dhan_row_parse_failed", extra={"error": str(exc)[:100]})

        registered = self.register_many(instruments)

        stats = {
            "total": len(rows),
            "registered": registered,
            "skipped": skipped,
        }
        logger.info(
            "dhan_instruments_loaded",
            extra=stats,
        )
        return stats

    def load_from_file(self, path: str | Path) -> dict[str, int]:
        """Load instruments from a local CSV file."""
        path = Path(path)
        if path.suffix == ".gz":
            with gzip.open(path, "rt", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
        else:
            with open(path, encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
        return self.load_from_rows(rows)

    def load_from_url(self, url: str) -> dict[str, int]:
        """Download and load instruments from a URL."""
        with urlopen(url) as resp:
            text = resp.read().decode("utf-8")
        rows = list(csv.DictReader(io.StringIO(text)))
        return self.load_from_rows(rows)

    def load_cached(self, force_refresh: bool = False) -> dict[str, int]:
        """Load from cache, downloading if stale or missing.

        Cache TTL: 6 hours (verified from archive).
        Old cache files older than 7 days are purged.
        """
        cache_dir = Path(os.environ.get("DHAN_CACHE_DIR", self.DEFAULT_CACHE_DIR))
        today = date.today()
        cache_file = cache_dir / f"instruments_{today.isoformat()}.csv"

        # Check for today's cache
        if not force_refresh and cache_file.exists():
            try:
                return self.load_from_file(cache_file)
            except Exception as exc:
                logger.warning("dhan_cache_load_failed", extra={"error": str(exc)[:100]})

        # Purge old cache files (> 7 days)
        self._purge_old_cache(cache_dir, max_days=7)

        # Download fresh
        try:
            with urlopen(self.INSTRUMENT_CSV_URL) as resp:
                text = resp.read().decode("utf-8")

            # Save to cache
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(text, encoding="utf-8")

            rows = list(csv.DictReader(io.StringIO(text)))
            return self.load_from_rows(rows)
        except Exception as exc:
            logger.error("dhan_download_failed", extra={"error": str(exc)[:200]})
            # Try to use any existing cache file as fallback
            fallback = self._find_latest_cache(cache_dir)
            if fallback is not None:
                logger.warning("dhan_using_stale_cache", extra={"path": str(fallback)})
                return self.load_from_file(fallback)
            raise

    # ── Row parsing ──────────────────────────────────────────────────────

    def _row_to_instrument(self, row: dict[str, Any]) -> ResolvedInstrument | None:
        """Parse a CSV row into a ResolvedInstrument."""
        trading_symbol = str(row.get(_COL_TRADING_SYMBOL, "")).strip()
        security_id = str(row.get(_COL_SECURITY_ID, "")).strip()

        if not trading_symbol or not security_id:
            return None

        # Security ID must be numeric for Dhan
        if not security_id.isdigit():
            return None

        # Map exchange segment
        exchange_code = str(row.get(_COL_EXCHANGE, "")).strip()
        segment = _COMPACT_SEGMENT_MAP.get(exchange_code, exchange_code)
        exchange = _SEGMENT_TO_EXCHANGE.get(segment, Exchange.NSE)

        # Map instrument type
        inst_name = str(row.get(_COL_INSTRUMENT_NAME, "")).strip().upper()
        instrument_type = _INSTRUMENT_NAME_TO_TYPE.get(inst_name, InstrumentType.EQUITY)

        # Parse lot size and tick size
        lot_size = _safe_int(row.get(_COL_LOT_UNITS), 1)
        tick_size = _safe_decimal(row.get(_COL_TICK_SIZE), Decimal("0.05")) or Decimal("0.05")

        # Parse expiry
        expiry = str(row.get(_COL_EXPIRY, "")).strip() or None

        # Parse strike price (for options)
        strike = _safe_decimal(row.get(_COL_STRIKE), None)

        # Parse option type
        str(row.get(_COL_OPTION_TYPE, "")).strip().upper()

        # Underlying symbol
        underlying = str(row.get(_COL_UNDERLYING, "")).strip()

        # Custom/canonical symbol
        custom_symbol = str(row.get(_COL_CUSTOM_SYMBOL, "")).strip()

        # Derive canonical symbol
        # For equities: use the trading symbol or custom symbol
        # For derivatives: use the underlying symbol
        if instrument_type == InstrumentType.EQUITY:
            canonical = custom_symbol or trading_symbol
        elif instrument_type == InstrumentType.INDEX:
            canonical = custom_symbol or trading_symbol
        else:
            canonical = underlying or custom_symbol or trading_symbol

        return ResolvedInstrument(
            symbol=canonical,
            exchange=exchange,
            broker_id=security_id,
            segment=segment,
            instrument_type=instrument_type,
            lot_size=lot_size,
            tick_size=tick_size,
            trading_symbol=trading_symbol,
            expiry=expiry,
            strike=strike,
            underlying=underlying,
        )

    # ── Alternate key generation (Dhan-specific) ─────────────────────────

    def _generate_alternate_keys(self, inst: ResolvedInstrument) -> list[str]:
        """Generate Dhan-specific alternate lookup keys."""
        keys = super()._generate_alternate_keys(inst)

        # Dhan-specific: add trading symbol variants
        ts = inst.trading_symbol
        if ts:
            stripped_ts = ts.replace(" ", "").replace("-", "").upper()
            keys.append(stripped_ts)

        # For options: add formatted variants with CE/PE
        if inst.instrument_type == InstrumentType.OPTIONS and inst.expiry and inst.strike is not None:
            underlying = inst.underlying or inst.symbol
            for suffix in ("CE", "PE", "CALL", "PUT"):
                compact = _build_dhan_option_key(underlying, inst.expiry, inst.strike, suffix)
                keys.append(compact)

        # For futures: add FUT suffix variant
        if inst.instrument_type == InstrumentType.FUTURES and inst.expiry:
            underlying = inst.underlying or inst.symbol
            compact = _build_dhan_future_key(underlying, inst.expiry)
            keys.append(compact)

        return keys

    # ── Cache helpers ────────────────────────────────────────────────────

    @staticmethod
    def _purge_old_cache(cache_dir: Path, max_days: int = 7) -> None:
        """Remove cache files older than max_days."""
        if not cache_dir.exists():
            return
        cutoff = date.today() - timedelta(days=max_days)
        for f in cache_dir.glob("instruments_*.csv"):
            try:
                date_str = f.stem.replace("instruments_", "")
                file_date = date.fromisoformat(date_str)
                if file_date < cutoff:
                    f.unlink()
            except (ValueError, OSError):
                pass

    @staticmethod
    def _find_latest_cache(cache_dir: Path) -> Path | None:
        """Find the most recent cache file."""
        if not cache_dir.exists():
            return None
        files = sorted(cache_dir.glob("instruments_*.csv"), reverse=True)
        return files[0] if files else None


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


def _build_dhan_option_key(underlying: str, expiry: str, strike: Decimal, suffix: str) -> str:
    """Build a Dhan-style compact option symbol."""
    parts = expiry.split("-")
    if len(parts) == 3:
        month_num = int(parts[1])
        months = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
        if 1 <= month_num <= 12:
            month = months[month_num - 1]
            year = parts[0][2:]
            strike_str = str(int(strike)) if strike == int(strike) else str(strike)
            return f"{underlying}{year}{month}{strike_str}{suffix}"
    return underlying


def _build_dhan_future_key(underlying: str, expiry: str) -> str:
    """Build a Dhan-style compact future symbol."""
    parts = expiry.split("-")
    if len(parts) == 3:
        month_num = int(parts[1])
        months = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
        if 1 <= month_num <= 12:
            month = months[month_num - 1]
            year = parts[0][2:]
            return f"{underlying}{year}{month}FUT"
    return underlying


__all__ = ["DhanInstrumentResolver"]
