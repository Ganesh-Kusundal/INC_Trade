"""Shared instrument resolution helpers (REF-08 extraction).

Consolidates the ``_generate_alternate_keys`` function that was
duplicated (with minor variations) in both the Dhan and Upstox
instrument resolvers.
"""

from __future__ import annotations

import logging
from typing import Any

from domain.symbols import normalize_symbol

from brokers.common.date_utils import format_expiry_components

logger = logging.getLogger(__name__)

_MONTH_ABBR = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
_MONTH_CHARS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "O", "N", "D"]


def generate_alternate_symbol_keys(
    symbol: str,
    inst_type: str,
    expiry: str | None = None,
    strike: Any = None,
    option_type: Any = None,
    underlying: str | None = None,
    canonical_symbol: str | None = None,
    sm_symbol_name: str | None = None,
    *,
    canonical_expand_call_put: bool = False,
    include_call_put_variants: bool = False,
    log_prefix: str = "alternate_key_generation_failed",
) -> list[str]:
    """Generate alternate symbol keys for fuzzy instrument resolution.

    This is the shared core of the ``_generate_alternate_keys`` methods
    in both Dhan's and Upstox's instrument resolvers.  It handles:

    - primary & canonical symbols
    - stripped symbols (remove spaces, dashes, underscores)
    - ``SM_SYMBOL_NAME`` (Dhan)
    - CALL/CE & PUT/PE standardisation
    - expiry-based keys for options and futures

    Parameters
    ----------
    symbol
        Primary trading symbol.
    inst_type
        Instrument type (e.g. ``"OPTION"``, ``"FUTURE"``).
    expiry
        Optional ISO expiry date (``"2026-06-20"``).
    strike
        Strike price (numeric or string).
    option_type
        Option type (e.g. ``"CE"``, ``"CALL"``, ``"PE"``, ``"PUT"``).
    underlying
        Underlying symbol.
    canonical_symbol
        Canonical / custom symbol from broker CSV.
    sm_symbol_name
        Dhan ``SM_SYMBOL_NAME`` field.
    canonical_expand_call_put
        Generate ``CE``/``PE`` variants from canonical symbol's ``CALL``/``PUT``.
    include_call_put_variants
        Generate ``CALL``/``PUT``-suffixed option keys (in addition to ``CE``/``PE``).
    log_prefix
        Prefix for debug log messages on failure.

    Returns
    -------
    list[str]
        Unique, normalised symbol keys in priority order.
    """
    keys: list[str] = []

    # 1. Primary symbol
    sym_up = normalize_symbol(symbol)
    keys.append(sym_up)

    # 2. Canonical symbol
    if canonical_symbol:
        canon_up = normalize_symbol(canonical_symbol)
        keys.append(canon_up)
        if canonical_expand_call_put:
            if canon_up.endswith(" CALL"):
                keys.append(canon_up[:-5] + " CE")
            elif canon_up.endswith(" PUT"):
                keys.append(canon_up[:-4] + " PE")

    # 3. Stripped symbol (no spaces, dashes, underscores)
    stripped = sym_up.replace(" ", "").replace("-", "").replace("_", "")
    keys.append(stripped)

    # 4. SM_SYMBOL_NAME (Dhan-specific)
    if sm_symbol_name:
        keys.append(normalize_symbol(sm_symbol_name))

    # Standardise option type and instrument type
    type_str = str(inst_type).upper()
    is_option = "OPT" in type_str or "OPTION" in type_str
    is_future = "FUT" in type_str or "FUTURE" in type_str

    if (is_option or is_future) and expiry and underlying:
        try:
            dd, dd_strip, mmm, yy, yyyy = format_expiry_components(expiry)
            month_char = _MONTH_CHARS[_MONTH_ABBR.index(mmm)]

            und_up = normalize_symbol(underlying)

            if is_option:
                opt_str = str(option_type).upper() if option_type else ""
                ce_pe = "CE" if "CALL" in opt_str or "CE" in opt_str or "C" in opt_str else "PE"

                # Format strike price
                strike_str = ""
                if strike is not None:
                    try:
                        st_val = float(strike)
                        strike_str = str(int(st_val)) if st_val % 1 == 0 else str(st_val)
                    except (ValueError, TypeError):
                        strike_str = str(strike)

                # Spaced option forms with CE/PE
                keys.append(f"{und_up} {dd} {mmm} {yy} {strike_str} {ce_pe}")
                keys.append(f"{und_up} {dd_strip} {mmm} {yy} {strike_str} {ce_pe}")
                keys.append(f"{und_up} {dd} {mmm} {yyyy} {strike_str} {ce_pe}")
                keys.append(f"{und_up} {dd_strip} {mmm} {yyyy} {strike_str} {ce_pe}")
                keys.append(f"{und_up} {dd} {mmm} {strike_str} {ce_pe}")
                keys.append(f"{und_up} {dd_strip} {mmm} {strike_str} {ce_pe}")

                # CALL/PUT variants (Dhan-specific)
                if include_call_put_variants:
                    call_put = "CALL" if ce_pe == "CE" else "PUT"
                    keys.append(f"{und_up} {dd} {mmm} {strike_str} {call_put}")
                    keys.append(f"{und_up} {dd_strip} {mmm} {strike_str} {call_put}")

                # Compact option forms
                keys.append(f"{und_up}{dd}{mmm}{yy}{strike_str}{ce_pe}")
                keys.append(f"{und_up}{dd_strip}{mmm}{yy}{strike_str}{ce_pe}")
                keys.append(f"{und_up}{dd}{mmm}{yyyy}{strike_str}{ce_pe}")
                keys.append(f"{und_up}{dd_strip}{mmm}{yyyy}{strike_str}{ce_pe}")
                keys.append(f"{und_up}{dd}{mmm}{strike_str}{ce_pe}")
                keys.append(f"{und_up}{dd_strip}{mmm}{strike_str}{ce_pe}")

                # Weekly format: e.g. NIFTY2662525000CE
                keys.append(f"{und_up}{yy}{month_char}{dd}{strike_str}{ce_pe}")
                keys.append(f"{und_up}{yy}{month_char}{dd_strip}{strike_str}{ce_pe}")

            elif is_future:
                keys.append(f"{und_up} {mmm} FUT")
                keys.append(f"{und_up} {yy} {mmm} FUT")
                keys.append(f"{und_up} {yyyy} {mmm} FUT")
                keys.append(f"{und_up} {dd} {mmm} FUT")
                keys.append(f"{und_up} FUT")

                keys.append(f"{und_up}{mmm}FUT")
                keys.append(f"{und_up}{yy}{mmm}FUT")
                keys.append(f"{und_up}{yyyy}{mmm}FUT")
                keys.append(f"{und_up}{dd}{mmm}FUT")
                keys.append(f"{und_up}FUT")
        except Exception as exc:
            logger.debug("%s: %s", log_prefix, exc)

    # Deduplicate while preserving order
    res: list[str] = []
    seen: set[str] = set()
    for k in keys:
        k_clean = normalize_symbol(k)
        if k_clean and k_clean not in seen:
            seen.add(k_clean)
            res.append(k_clean)
    return res
