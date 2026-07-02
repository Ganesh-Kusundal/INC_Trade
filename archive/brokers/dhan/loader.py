"""Instrument master CSV loader with daily cache + MCX detailed supplement."""

from __future__ import annotations

import logging
import os
import time
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from brokers.dhan.segments import _COMPACT_SEGMENT_MAP
from domain.symbols import normalize_exchange
from config.endpoints import Dhan

logger = logging.getLogger(__name__)

_COMPACT_CSV_URL = Dhan.INSTRUMENT_CSV
_DETAILED_MCX_URL = Dhan.INSTRUMENT_MCX_DETAILED


class InstrumentLoader:
    """Downloads and parses Dhan instrument master with daily caching."""

    @staticmethod
    def _cleanup_old_cache(cache_dir: Path, days: int = 7) -> None:
        """Purge cached files older than N days."""
        now = time.time()
        cutoff = now - (days * 24 * 3600)
        try:
            for path in cache_dir.glob("instruments_*.csv"):
                if path.is_file():
                    mtime = path.stat().st_mtime
                    if mtime < cutoff:
                        logger.info("Cleaning up old instrument cache file: %s", path)
                        path.unlink(missing_ok=True)
        except Exception as exc:
            logger.warning("Failed to clean up old cache files: %s", exc)

    @staticmethod
    def load_cached(force_refresh: bool = False, *, mcx_required: bool | None = None) -> list[dict]:
        """Load instrument master rows with daily caching.

        Parameters
        ----------
        force_refresh:
            If True, ignore the on-disk cache and re-download.
        mcx_required:
            When True, the MCX detailed fetch is mandatory and the
            loader raises if it fails. When False, MCX failures are
            logged and skipped. When None (the default), the loader
            uses the environment variable ``DHAN_TRADING_SEGMENTS``:
            if the comma-separated list contains ``MCX``, MCX is
            required; otherwise MCX failures are non-fatal.

            This closes the silent-failure hotspot in
            ``_fetch_mcx_detailed`` for commodity traders. The
            previous behaviour (non-fatal on failure) was a documented
            risk in the architecture review.
        """
        # Use environment variable if set, otherwise compute default from project root
        env_cache = os.environ.get("DHAN_CACHE_DIR")
        if env_cache:
            cache_dir = Path(env_cache)
        else:
            # Default to project-root/runtime-dev/instruments
            # loader.py is in brokers/dhan/loader.py, so parents[2] is project root
            cache_dir = Path(__file__).resolve().parents[2] / "runtime-dev" / "instruments"

        cache_dir.mkdir(parents=True, exist_ok=True)

        # Clean up old caches (older than 7 days)
        InstrumentLoader._cleanup_old_cache(cache_dir, days=7)

        today = date.today().isoformat()
        cache_path = cache_dir / f"instruments_{today}.csv"

        # Check Cache TTL (6 hours)
        if not force_refresh and cache_path.exists() and cache_path.stat().st_size > 0:
            try:
                mtime = datetime.fromtimestamp(cache_path.stat().st_mtime)
                cache_age_hours = (datetime.now() - mtime).total_seconds() / 3600.0
                if cache_age_hours > 6.0:
                    logger.info(
                        "Cache is older than 6 hours (age: %.1f hours). Attempting refresh...",
                        cache_age_hours,
                    )
                    force_refresh = True
            except Exception as exc:
                logger.warning("Error checking cache file modification time: %s", exc)

        df = None
        if not force_refresh and cache_path.exists() and cache_path.stat().st_size > 0:
            logger.info("Loading instruments from cache: %s", cache_path)
            try:
                df = pd.read_csv(cache_path, low_memory=False)
            except Exception as exc:
                logger.warning("Failed to read cached file: %s. Will re-download.", exc)

        if df is None:
            logger.info("Downloading instruments from Dhan...")
            try:
                df = pd.read_csv(_COMPACT_CSV_URL, low_memory=False)
                tmp_path = cache_path.with_suffix(".csv.tmp")
                df.to_csv(tmp_path, index=False)
                os.replace(tmp_path, cache_path)
            except Exception as exc:
                if cache_path.exists() and cache_path.stat().st_size > 0:
                    logger.error(
                        "Failed to download instruments from Dhan (%s). Falling back to stale cached file.",
                        exc,
                    )
                    try:
                        df = pd.read_csv(cache_path, low_memory=False)
                    except Exception as read_exc:
                        raise exc from read_exc
                else:
                    raise exc

        rows = InstrumentLoader._compact_to_rows(df)

        # Resolve whether MCX is mandatory. ``None`` (the default)
        # looks at the operator's env var; the explicit boolean wins.
        if mcx_required is None:
            trading_segments = os.environ.get("DHAN_TRADING_SEGMENTS", "")
            mcx_required = "MCX" in [
                normalize_exchange(s) for s in trading_segments.split(",") if s.strip()
            ]

        # Supplement with MCX detailed API (has GOLD/CRUDEOIL futures
        # missing from compact). The behaviour on failure is now
        # configurable via ``mcx_required`` — see the docstring.
        try:
            mcx_rows = InstrumentLoader._fetch_mcx_detailed()
        except Exception as exc:
            if mcx_required:
                logger.error("MCX detailed fetch FAILED and is required: %s", exc)
                raise
            logger.warning("MCX detailed fetch failed (non-fatal): %s", exc)
            mcx_rows = []

        if mcx_rows:
            existing_idx = {r["SEM_SMST_SECURITY_ID"]: i for i, r in enumerate(rows)}
            added = 0
            replaced = 0
            for r in mcx_rows:
                sid = r.get("SEM_SMST_SECURITY_ID")
                if not sid:
                    continue
                i = existing_idx.get(sid)
                if i is None:
                    rows.append(r)
                    existing_idx[sid] = len(rows) - 1
                    added += 1
                else:
                    rows[i] = r
                    replaced += 1
            logger.info(
                "Merged %d MCX instruments (added=%d replaced=%d)", len(mcx_rows), added, replaced
            )

        return rows

    @staticmethod
    def load_from_file(path: str | Path) -> list[dict]:
        df = pd.read_csv(path, low_memory=False)
        return InstrumentLoader._compact_to_rows(df)

    @staticmethod
    def load_from_url(url: str) -> list[dict]:
        df = pd.read_csv(url, low_memory=False)
        return InstrumentLoader._compact_to_rows(df)

    @staticmethod
    def _compact_to_rows(df) -> list[dict]:
        out: list[dict] = []
        for r in df.itertuples(index=False):
            exch_id = str(getattr(r, "SEM_EXM_EXCH_ID", ""))
            segment = str(getattr(r, "SEM_SEGMENT", ""))
            seg = _COMPACT_SEGMENT_MAP.get((exch_id, segment))
            if seg is None:
                continue
            out.append(
                {
                    "SEM_TRADING_SYMBOL": str(getattr(r, "SEM_TRADING_SYMBOL", "")),
                    "SEM_SMST_SECURITY_ID": str(int(getattr(r, "SEM_SMST_SECURITY_ID", 0))),
                    "SEM_EXM_EXCH_ID": seg,
                    "SEM_INSTRUMENT_NAME": str(getattr(r, "SEM_INSTRUMENT_NAME", "")),
                    "SEM_LOT_UNITS": _safe_float(r, "SEM_LOT_UNITS", 1),
                    "SEM_TICK_SIZE": _safe_float(r, "SEM_TICK_SIZE", 0.05),
                    "SEM_EXPIRY_DATE": _safe_str(r, "SEM_EXPIRY_DATE"),
                    "SEM_STRIKE_PRICE": _safe_opt_float(r, "SEM_STRIKE_PRICE"),
                    "SEM_OPTION_TYPE": _safe_opt_str(r, "SEM_OPTION_TYPE"),
                    "SEM_CUSTOM_SYMBOL": _safe_opt_str(r, "SEM_CUSTOM_SYMBOL"),
                    "SM_SYMBOL_NAME": _safe_opt_str(r, "SM_SYMBOL_NAME"),
                }
            )
        return out

    @staticmethod
    def _fetch_mcx_detailed() -> list[dict]:
        """Fetch MCX instruments from Dhan's detailed segment API.

        The compact CSV is missing many MCX futures (GOLD, CRUDEOIL, etc.).
        The detailed API at /v2/instrument/MCX_COMM has them with
        UNDERLYING_SECURITY_ID needed for option chain calls.
        """
        import csv
        import io
        import urllib.request

        req = urllib.request.Request(
            _DETAILED_MCX_URL,
            headers={"User-Agent": "TradeXV2/1.0"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = resp.read().decode("utf-8")

        reader = csv.DictReader(io.StringIO(content))
        rows: list[dict] = []
        for r in reader:
            if r.get("SEGMENT") != "M":
                continue

            symbol_name = (r.get("SYMBOL_NAME") or "").strip()
            instrument = (r.get("INSTRUMENT") or "").strip()
            expiry_date_str = (r.get("SM_EXPIRY_DATE") or "").strip()
            strike_price_str = (r.get("STRIKE_PRICE") or "").strip()
            option_type = (r.get("OPTION_TYPE") or "").strip()
            display_name = (r.get("DISPLAY_NAME") or "").strip()

            # Construct trading symbol if possible
            trading_symbol = symbol_name
            if expiry_date_str:
                try:
                    from datetime import datetime

                    dt_str = expiry_date_str.split()[0]
                    dt = datetime.strptime(dt_str, "%Y-%m-%d")
                    dd_mmm_yyyy = dt.strftime("%d%b%Y")

                    if "FUT" in instrument.upper() and "OPT" not in instrument.upper():
                        trading_symbol = f"{symbol_name.upper()}-{dd_mmm_yyyy}-FUT"
                    elif "OPT" in instrument.upper():
                        try:
                            st = float(strike_price_str)
                            st_str = str(int(st)) if st % 1 == 0 else str(st)
                        except (ValueError, TypeError):
                            st_str = strike_price_str

                        opt = option_type.upper()
                        if opt == "XX":
                            opt = ""
                        trading_symbol = f"{symbol_name.upper()}-{dd_mmm_yyyy}-{st_str}-{opt}"
                except Exception as exc:
                    logger.debug("mcx_symbol_parse_failed: %s", exc)

            rows.append(
                {
                    "SEM_TRADING_SYMBOL": trading_symbol,
                    "SEM_SMST_SECURITY_ID": (r.get("SECURITY_ID") or "").strip(),
                    "SEM_EXM_EXCH_ID": "MCX_COMM",
                    "SEM_INSTRUMENT_NAME": instrument,
                    "SEM_LOT_UNITS": _safe_float_dict(r, "LOT_SIZE", 1),
                    "SEM_TICK_SIZE": _safe_float_dict(r, "TICK_SIZE", 0.05),
                    "SEM_EXPIRY_DATE": expiry_date_str or None,
                    "SEM_STRIKE_PRICE": strike_price_str or None,
                    "SEM_OPTION_TYPE": option_type or None,
                    "SEM_CUSTOM_SYMBOL": display_name or None,
                    "SM_SYMBOL_NAME": symbol_name.upper() if symbol_name else None,
                }
            )
        return rows


def _safe_float(r, col: str, default):
    val = getattr(r, col, None)
    return val if pd.notna(val) else default


def _safe_str(r, col: str):
    val = getattr(r, col, None)
    return str(val) if pd.notna(val) else None


def _safe_opt_float(r, col: str):
    val = getattr(r, col, None)
    return val if pd.notna(val) else None


def _safe_opt_str(r, col: str):
    val = getattr(r, col, None)
    return str(val) if pd.notna(val) else None


def _safe_float_dict(r: dict, col: str, default):
    try:
        val = r.get(col, "")
        if val is None or val == "":
            return default
        return float(val)
    except (TypeError, ValueError):
        return default
