"""Dhan instrument master CSV loader with disk cache and MCX supplement.

Downloads and caches the compact Dhan scrip master CSV. Optionally fetches the
MCX detailed segment feed and merges it into the compact CSV text before the
resolver parses rows.

Parsing of instrument rows is owned by ``DhanInstrumentResolver``; this module
only handles download, cache lifecycle, and MCX supplement merge.
"""

from __future__ import annotations

import csv
import io
import logging
import os
import time
from datetime import date, datetime
from pathlib import Path

import requests
from brokers_core.config.endpoints import Dhan

logger = logging.getLogger(__name__)

_COMPACT_CSV_URL = Dhan.INSTRUMENT_CSV
_DETAILED_MCX_URL = Dhan.INSTRUMENT_MCX_DETAILED
_CACHE_TTL_HOURS = 6.0
_CACHE_CLEANUP_DAYS = 7

# Compact CSV columns written for MCX supplement rows.
_COMPACT_FIELDS = (
    "SEM_TRADING_SYMBOL",
    "SEM_SMST_SECURITY_ID",
    "SEM_EXM_EXCH_ID",
    "SEM_INSTRUMENT_NAME",
    "SEM_LOT_UNITS",
    "SEM_TICK_SIZE",
    "SEM_EXPIRY_DATE",
    "SEM_STRIKE_PRICE",
    "SEM_OPTION_TYPE",
)


class InstrumentLoader:
    """Downloads and caches Dhan instrument master CSV text."""

    @staticmethod
    def resolve_cache_dir() -> Path:
        """Return cache directory from ``DHAN_CACHE_DIR`` or project default."""
        env_cache = os.environ.get("DHAN_CACHE_DIR")
        if env_cache:
            return Path(env_cache)
        # instrument_loader.py lives at brokers/adapters/dhan/ → parents[3] is repo root
        return Path(__file__).resolve().parents[3] / "runtime-dev" / "instruments"

    @classmethod
    def load_csv_text(
        cls,
        force_refresh: bool = False,
        *,
        mcx_required: bool | None = None,
        mcx_csv_path: Path | str | None = None,
    ) -> str:
        """Load compact instrument CSV text with optional MCX supplement.

        Parameters
        ----------
        force_refresh:
            Ignore on-disk cache and re-download the compact master CSV.
        mcx_required:
            When True, MCX detailed fetch failures raise. When False, failures are
            logged and skipped. When None, ``DHAN_TRADING_SEGMENTS`` decides:
            MCX is required when the comma-separated list contains ``MCX``.
        mcx_csv_path:
            Optional local MCX detailed CSV for tests; bypasses HTTP when set.
        """
        cache_dir = cls.resolve_cache_dir()
        cache_dir.mkdir(parents=True, exist_ok=True)
        cls._cleanup_old_cache(cache_dir, days=_CACHE_CLEANUP_DAYS)

        today = date.today().isoformat()
        cache_path = cache_dir / f"instruments_{today}.csv"

        if not force_refresh and cache_path.exists() and cache_path.stat().st_size > 0:
            try:
                mtime = datetime.fromtimestamp(cache_path.stat().st_mtime)
                cache_age_hours = (datetime.now() - mtime).total_seconds() / 3600.0
                if cache_age_hours > _CACHE_TTL_HOURS:
                    logger.info(
                        "Cache is older than %.0f hours (age: %.1f hours). Attempting refresh...",
                        _CACHE_TTL_HOURS,
                        cache_age_hours,
                    )
                    force_refresh = True
            except OSError as exc:
                logger.warning("Error checking cache file modification time: %s", exc)

        compact_text: str | None = None
        if not force_refresh and cache_path.exists() and cache_path.stat().st_size > 0:
            logger.info("Loading instruments from cache: %s", cache_path)
            try:
                compact_text = cache_path.read_text(encoding="utf-8")
            except OSError as exc:
                logger.warning("Failed to read cached file: %s. Will re-download.", exc)

        if compact_text is None:
            logger.info("Downloading instruments from Dhan...")
            try:
                compact_text = cls._download_compact_csv()
                tmp_path = cache_path.with_suffix(".csv.tmp")
                tmp_path.write_text(compact_text, encoding="utf-8")
                os.replace(tmp_path, cache_path)
            except Exception as exc:
                if cache_path.exists() and cache_path.stat().st_size > 0:
                    logger.error(
                        "Failed to download instruments from Dhan (%s). "
                        "Falling back to stale cached file.",
                        exc,
                    )
                    compact_text = cache_path.read_text(encoding="utf-8")
                else:
                    raise

        if mcx_required is None:
            trading_segments = os.environ.get("DHAN_TRADING_SEGMENTS", "")
            mcx_required = "MCX" in [
                s.strip().upper() for s in trading_segments.split(",") if s.strip()
            ]

        try:
            if mcx_csv_path is not None:
                mcx_text = Path(mcx_csv_path).read_text(encoding="utf-8")
            else:
                mcx_text = cls._download_mcx_detailed_csv()
            mcx_rows = cls._parse_mcx_detailed_csv(mcx_text)
        except Exception as exc:
            if mcx_required:
                logger.error("MCX detailed fetch FAILED and is required: %s", exc)
                raise
            logger.warning("MCX detailed fetch failed (non-fatal): %s", exc)
            mcx_rows = []

        if mcx_rows:
            compact_text = cls._merge_mcx_rows(compact_text, mcx_rows)

        return compact_text

    @staticmethod
    def _cleanup_old_cache(cache_dir: Path, days: int = 7) -> None:
        """Purge cached files older than N days."""
        now = time.time()
        cutoff = now - (days * 24 * 3600)
        try:
            for path in cache_dir.glob("instruments_*.csv"):
                if path.is_file() and path.stat().st_mtime < cutoff:
                    logger.info("Cleaning up old instrument cache file: %s", path)
                    path.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("Failed to clean up old cache files: %s", exc)

    @staticmethod
    def _download_compact_csv() -> str:
        resp: requests.Response = requests.get(_COMPACT_CSV_URL, timeout=30)
        resp.raise_for_status()
        return resp.text

    @staticmethod
    def _download_mcx_detailed_csv() -> str:
        resp: requests.Response = requests.get(
            _DETAILED_MCX_URL,
            timeout=30,
            headers={"User-Agent": "TradeXV2/1.0"},
        )
        resp.raise_for_status()
        return resp.text

    @staticmethod
    def _parse_mcx_detailed_csv(content: str) -> list[dict[str, str]]:
        """Parse MCX detailed segment CSV into compact-format row dicts."""
        reader = csv.DictReader(io.StringIO(content))
        rows: list[dict[str, str]] = []
        for r in reader:
            if (r.get("SEGMENT") or "").strip() != "M":
                continue

            symbol_name = (r.get("SYMBOL_NAME") or "").strip()
            instrument = (r.get("INSTRUMENT") or "").strip()
            expiry_date_str = (r.get("SM_EXPIRY_DATE") or "").strip()
            strike_price_str = (r.get("STRIKE_PRICE") or "").strip()
            option_type = (r.get("OPTION_TYPE") or "").strip()

            trading_symbol = symbol_name
            if expiry_date_str:
                try:
                    dt_str = expiry_date_str.split()[0]
                    dt = datetime.strptime(dt_str, "%Y-%m-%d")
                    dd_mmm_yyyy = dt.strftime("%d%b%Y")

                    instrument_upper = instrument.upper()
                    if "FUT" in instrument_upper and "OPT" not in instrument_upper:
                        trading_symbol = f"{symbol_name.upper()}-{dd_mmm_yyyy}-FUT"
                    elif "OPT" in instrument_upper:
                        try:
                            strike = float(strike_price_str)
                            strike_str = (
                                str(int(strike)) if strike % 1 == 0 else str(strike)
                            )
                        except (TypeError, ValueError):
                            strike_str = strike_price_str
                        opt = option_type.upper()
                        if opt == "XX":
                            opt = ""
                        trading_symbol = (
                            f"{symbol_name.upper()}-{dd_mmm_yyyy}-{strike_str}-{opt}"
                        )
                except (ValueError, TypeError) as exc:
                    logger.debug("mcx_symbol_parse_failed: %s", exc)

            security_id = (r.get("SECURITY_ID") or "").strip()
            if not security_id:
                continue

            rows.append(
                {
                    "SEM_TRADING_SYMBOL": trading_symbol,
                    "SEM_SMST_SECURITY_ID": security_id,
                    "SEM_EXM_EXCH_ID": "MCX",
                    "SEM_INSTRUMENT_NAME": instrument,
                    "SEM_LOT_UNITS": _safe_float_str(r.get("LOT_SIZE"), "1"),
                    "SEM_TICK_SIZE": _safe_float_str(r.get("TICK_SIZE"), "0.05"),
                    "SEM_EXPIRY_DATE": expiry_date_str,
                    "SEM_STRIKE_PRICE": strike_price_str,
                    "SEM_OPTION_TYPE": option_type,
                }
            )
        return rows

    @staticmethod
    def _merge_mcx_rows(compact_text: str, mcx_rows: list[dict[str, str]]) -> str:
        """Merge MCX supplement rows into compact CSV text by security_id."""
        reader = csv.DictReader(io.StringIO(compact_text))
        fieldnames = list(reader.fieldnames or _COMPACT_FIELDS)
        for col in _COMPACT_FIELDS:
            if col not in fieldnames:
                fieldnames.append(col)

        rows_by_id: dict[str, dict[str, str]] = {}
        for row in reader:
            sid = (row.get("SEM_SMST_SECURITY_ID") or "").strip().split(".")[0]
            if sid:
                rows_by_id[sid] = row

        added = 0
        replaced = 0
        for mcx_row in mcx_rows:
            sid = (mcx_row.get("SEM_SMST_SECURITY_ID") or "").strip()
            if not sid:
                continue
            if sid in rows_by_id:
                rows_by_id[sid].update(mcx_row)
                replaced += 1
            else:
                rows_by_id[sid] = dict(mcx_row)
                added += 1

        logger.info(
            "Merged %d MCX instruments (added=%d replaced=%d)",
            len(mcx_rows),
            added,
            replaced,
        )

        out = io.StringIO()
        writer = csv.DictWriter(out, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows_by_id.values())
        return out.getvalue()


def _safe_float_str(value: str | float | int | None, default: str) -> str:
    try:
        if value is None or value == "":
            return default
        return str(float(value))
    except (TypeError, ValueError):
        return default
