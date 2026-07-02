"""Dhan symbol-mapping and validation layer."""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Any

from brokers.dhan.domain import Exchange, InstrumentType, OptionType
from brokers.dhan.loader import InstrumentLoader
from brokers.dhan.resolver import SymbolResolver
from domain.symbols import normalize_symbol

logger = logging.getLogger(__name__)

# Regex patterns for F&O symbol parsing
# Format 1: "NIFTY 26 JUN 25000 CE" or "BANKNIFTY 24 JUL 55000 PE"
_OPT_SPACED_PATTERN = re.compile(
    r"^([A-Z0-9\-_]+)\s+(\d{1,2})\s+([A-Z]{3})\s+(\d+(?:\.\d+)?)\s+(CE|PE|CALL|PUT)$", re.IGNORECASE
)

# Format 2: "NIFTY26JUN25000CE"
_OPT_COMPACT_PATTERN = re.compile(
    r"^([A-Z0-9\-_]+?)(\d{1,2})([A-Z]{3})(\d+(?:\.\d+)?)(CE|PE|CALL|PUT)$", re.IGNORECASE
)

# Format 3: Futures with day: "CRUDEOIL 24 JUN FUT"
_FUT_SPACED_DAY_PATTERN = re.compile(
    r"^([A-Z0-9\-_]+)\s+(\d{1,2})\s+([A-Z]{3})\s+(FUT|FUTURES)$", re.IGNORECASE
)

# Format 4: Futures without day: "CRUDEOIL JUN FUT"
_FUT_SPACED_NO_DAY_PATTERN = re.compile(
    r"^([A-Z0-9\-_]+)\s+([A-Z]{3})\s+(FUT|FUTURES)$", re.IGNORECASE
)

_MONTH_MAP = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}


def parse_fo_symbol(symbol: str) -> dict[str, Any] | None:
    """Parse a symbol string to extract F&O fields.

    Returns a dict with:
      underlying, expiry_day, expiry_month, strike, option_type, is_future
    or None if it doesn't match F&O formats.
    """
    clean = normalize_symbol(symbol)

    # 1. Spaced Option
    m = _OPT_SPACED_PATTERN.match(clean)
    if m:
        underlying, day, month, strike, opt_type = m.groups()
        return {
            "underlying": underlying,
            "expiry_day": int(day),
            "expiry_month": month.upper(),
            "strike": float(strike),
            "option_type": "CE" if opt_type in ("CE", "CALL") else "PE",
            "is_future": False,
        }

    # 2. Compact Option
    m = _OPT_COMPACT_PATTERN.match(clean)
    if m:
        underlying, day, month, strike, opt_type = m.groups()
        return {
            "underlying": underlying,
            "expiry_day": int(day),
            "expiry_month": month.upper(),
            "strike": float(strike),
            "option_type": "CE" if opt_type in ("CE", "CALL") else "PE",
            "is_future": False,
        }

    # 3. Spaced Future with Day
    m = _FUT_SPACED_DAY_PATTERN.match(clean)
    if m:
        underlying, day, month, _ = m.groups()
        return {
            "underlying": underlying,
            "expiry_day": int(day),
            "expiry_month": month.upper(),
            "strike": None,
            "option_type": None,
            "is_future": True,
        }

    # 4. Spaced Future without Day
    m = _FUT_SPACED_NO_DAY_PATTERN.match(clean)
    if m:
        underlying, month, _ = m.groups()
        return {
            "underlying": underlying,
            "expiry_day": None,
            "expiry_month": month.upper(),
            "strike": None,
            "option_type": None,
            "is_future": True,
        }

    return None


class DhanSymbolValidator:
    """Validator for DhanHQ symbol mapping and verification."""

    def __init__(self, resolver: SymbolResolver | None = None) -> None:
        if resolver is None:
            self.resolver = SymbolResolver()
            rows = InstrumentLoader.load_cached()
            self.resolver.load_from_rows(rows)
        else:
            self.resolver = resolver

    def validate(
        self, symbol: str, exchange: str | None = None, segment: str | None = None
    ) -> dict[str, Any]:
        """Normalize, match against the instrument master, and validate the symbol.

        Handles both standard equity/indices and F&O symbols.
        """
        # 1. Normalize Symbol
        normalized_sym = normalize_symbol(symbol)

        # Check if F&O
        fo_info = parse_fo_symbol(normalized_sym)

        if fo_info:
            return self._validate_fo(normalized_sym, fo_info, exchange, segment)
        else:
            return self._validate_standard(normalized_sym, exchange, segment)

    def _validate_standard(
        self, symbol: str, exchange_filter: str | None = None, segment_filter: str | None = None
    ) -> dict[str, Any]:
        """Validate standard equity/index symbols."""
        candidates = []

        exchanges_to_check = (
            [exchange_filter]
            if exchange_filter
            else ["NSE", "BSE", "INDEX", "MCX", "CDS", "NFO", "BFO"]
        )

        for exch_str in exchanges_to_check:
            try:
                inst = self.resolver.resolve(symbol, exch_str)
                if inst:
                    # Apply segment filter if provided
                    segment_val = self._get_segment_code(inst.exchange, inst.instrument_type)
                    if segment_filter and segment_filter.upper() != segment_val:
                        continue

                    candidates.append(
                        {
                            "exchange": inst.exchange.value,
                            "segment": segment_val,
                            "tradingSymbol": inst.symbol,
                            "displayName": inst.canonical_symbol
                            or f"{inst.symbol}-{inst.exchange.value}",
                            "securityId": inst.security_id,
                            "instrumentType": self._get_inst_type_code(inst.instrument_type),
                        }
                    )
            except Exception:
                logger.debug("symbol_candidate_build_failed: %s", inst.symbol)

        if not candidates:
            # Check for partial matches or underlying name
            all_insts = self.resolver.all_instruments()
            partial_matches = [
                i
                for i in all_insts
                if symbol == (i.underlying or "").upper()
                or symbol in i.symbol.upper()
                or (i.canonical_symbol and symbol in i.canonical_symbol.upper())
            ]

            if partial_matches:
                # Format partial matches as candidates
                for inst in partial_matches[:10]:
                    candidates.append(
                        {
                            "exchange": inst.exchange.value,
                            "segment": self._get_segment_code(inst.exchange, inst.instrument_type),
                            "tradingSymbol": inst.symbol,
                            "displayName": inst.canonical_symbol
                            or f"{inst.symbol}-{inst.exchange.value}",
                            "securityId": inst.security_id,
                            "instrumentType": self._get_inst_type_code(inst.instrument_type),
                        }
                    )
                return {
                    "status": "AMBIGUOUS",
                    "message": f"Multiple candidates found for '{symbol}'. Please specify a specific contract.",
                    "candidates": candidates,
                }

            return {
                "status": "INVALID",
                "message": f"Symbol '{symbol}' not found in Dhan instrument master.",
                "candidates": [],
            }

        if len(candidates) > 1:
            # Check if there is a primary one or return candidates
            return {
                "status": "AMBIGUOUS",
                "message": f"Multiple matches found for symbol '{symbol}'. Please specify exchange or segment.",
                "candidates": candidates,
            }

        # Unique match
        res = candidates[0]
        res["status"] = "VALID"
        return res

    def _validate_fo(
        self,
        symbol: str,
        fo_info: dict[str, Any],
        exchange_filter: str | None = None,
        segment_filter: str | None = None,
    ) -> dict[str, Any]:
        """Validate F&O derivatives (options and futures)."""
        underlying = fo_info["underlying"]
        exp_day = fo_info["expiry_day"]
        exp_month = fo_info["expiry_month"]
        strike = fo_info["strike"]
        opt_type = fo_info["option_type"]
        is_future = fo_info["is_future"]

        # 1. Search Dhan instrument master
        all_insts = self.resolver.all_instruments()

        matches = []
        for inst in all_insts:
            # Check underlying name
            inst_und = inst.underlying or ""
            if not inst_und and "-" in inst.symbol:
                inst_und = inst.symbol.split("-")[0]
            if not inst_und and inst.canonical_symbol:
                inst_und = inst.canonical_symbol.split()[0]

            if inst_und.upper() != underlying:
                continue

            # Check instrument type
            if is_future and not inst.is_future:
                continue
            if not is_future and not inst.is_option:
                continue

            # Check strike price
            if strike is not None:
                if inst.strike_price is None:
                    continue
                # Compare strike prices using float conversion
                if abs(float(inst.strike_price) - strike) > 0.01:
                    continue

            # Check option type
            if opt_type is not None:
                if inst.option_type is None:
                    continue
                inst_opt_type = "CALL" if inst.option_type == OptionType.CALL else "PUT"
                if inst_opt_type != opt_type:
                    continue

            # Check expiry month and day
            if inst.expiry:
                try:
                    dt = datetime.strptime(inst.expiry[:10], "%Y-%m-%d")
                    inst_month = dt.strftime("%b").upper()
                    inst_day = dt.day

                    if inst_month != exp_month:
                        continue
                    if exp_day is not None and inst_day != exp_day:
                        continue
                except Exception:
                    continue
            else:
                continue

            matches.append(inst)

        # Handle filter matching
        if exchange_filter:
            matches = [m for m in matches if m.exchange.value == exchange_filter.upper()]
        if segment_filter:
            matches = [
                m
                for m in matches
                if self._get_segment_code(m.exchange, m.instrument_type) == segment_filter.upper()
            ]

        # Verify month code exists in month map
        month_num = _MONTH_MAP.get(exp_month)
        if not month_num:
            return {
                "underlying": underlying,
                "expiry": f"INVALID_MONTH_{exp_month}",
                "strike": strike,
                "optionType": opt_type,
                "status": "INVALID_EXPIRY_FORMAT",
                "message": f"Expiry month '{exp_month}' is not recognized.",
            }

        # If no active match is found, check if it's expired
        if not matches:
            # Estimate expiry date to see if it's in the past
            # Check years 2024, 2025, 2026, 2027 etc.
            # If a weekly expiry, it usually falls on a Wednesday or Thursday.
            likely_year = None
            current_yr = datetime.now().year

            # Find a year where the day of the week matches typical F&O expiry days (Wed/Thu)
            # or default to current year
            target_day = exp_day if exp_day is not None else 25  # fallback
            for yr in [2024, 2025, 2026, 2027, 2028, 2029]:
                try:
                    d = date(yr, month_num, target_day)
                    # Thursday (3) or Wednesday (2) or Tuesday (1)
                    if d.weekday() in (1, 2, 3):
                        likely_year = yr
                        break
                except ValueError:
                    continue

            if not likely_year:
                likely_year = current_yr

            expiry_str = f"{likely_year}-{month_num:02d}-{target_day:02d}"
            try:
                expiry_date = date(likely_year, month_num, target_day)
                is_past = expiry_date < date.today()
            except ValueError:
                is_past = True

            status = "EXPIRED" if is_past else "INVALID"
            message = (
                f"Option contract expired on {expiry_str} and is no longer present in the active Dhan instrument master."
                if is_past
                else f"No instrument matching '{symbol}' was found in the active master list."
            )

            return {
                "underlying": underlying,
                "expiry": expiry_str,
                "strike": strike,
                "optionType": opt_type,
                "securityId": None,
                "exchange": "NFO" if underlying in ("NIFTY", "BANKNIFTY", "FINNIFTY") else "MCX",
                "segment": "D" if underlying in ("NIFTY", "BANKNIFTY", "FINNIFTY") else "M",
                "lotSize": None,
                "status": status,
                "message": message,
            }

        # If multiple matches, flag ambiguity
        if len(matches) > 1:
            candidates = []
            for inst in matches:
                candidates.append(
                    {
                        "securityId": inst.security_id,
                        "tradingSymbol": inst.symbol,
                        "exchange": inst.exchange.value,
                        "segment": self._get_segment_code(inst.exchange, inst.instrument_type),
                        "lotSize": inst.lot_size,
                    }
                )
            return {
                "underlying": underlying,
                "expiry": matches[0].expiry[:10] if matches[0].expiry else None,
                "strike": strike,
                "optionType": opt_type,
                "status": "AMBIGUOUS",
                "message": "Multiple matching instruments found in active master.",
                "candidates": candidates,
            }

        # Unique active match
        inst = matches[0]
        return {
            "underlying": underlying,
            "expiry": inst.expiry[:10] if inst.expiry else None,
            "strike": float(inst.strike_price) if inst.strike_price is not None else None,
            "optionType": opt_type,
            "securityId": inst.security_id,
            "exchange": inst.exchange.value,
            "segment": self._get_segment_code(inst.exchange, inst.instrument_type),
            "lotSize": inst.lot_size,
            "status": "VALID",
        }

    @staticmethod
    def _get_segment_code(exchange: Exchange, inst_type: InstrumentType) -> str:
        """Map exchange + instrument type to segment code: E, D, C, M."""
        if exchange == Exchange.MCX:
            return "M"
        if exchange == Exchange.CDS:
            return "C"
        if exchange in (Exchange.NFO, Exchange.BFO):
            return "D"
        # Equity exchange
        if inst_type == InstrumentType.EQUITY:
            return "E"
        # Derivative/FNO
        return "D"

    @staticmethod
    def _get_inst_type_code(inst_type: InstrumentType) -> str:
        """Return canonical instrument type code."""
        if inst_type == InstrumentType.EQUITY:
            return "EQ"
        if inst_type == InstrumentType.FUTURE:
            return "FUT"
        if inst_type == InstrumentType.OPTION:
            return "OPT"
        return inst_type.value
