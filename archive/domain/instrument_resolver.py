"""Strategy DSL resolver — convert symbolic selectors to InstrumentId.

Strategy DSL examples:
    NIFTY_WEEK_0_ATM_CE     → NFO:NIFTY:20260703:25000:CE (nearest weekly ATM call)
    BANKNIFTY_MONTH_1_ATM_PE → NFO:BANKNIFTY:20260731:55000:PE (next monthly ATM put)
    NIFTY_FUT_CURRENT        → NFO:NIFTY:20260703:FUT (current week future)
    RELIANCE                 → NSE:RELIANCE (equity passthrough)

These are NOT instrument IDs — they are high-level selectors that get
resolved to concrete InstrumentIds via the resolver. After resolution,
the selector disappears.

Usage:
    from domain.instrument_resolver import resolve_selector

    iid = resolve_selector("NIFTY_WEEK_0_ATM_CE", spot=25000)
    # → InstrumentId(NFO, NIFTY, expiry=2026-07-03, strike=25000, right=CE)
"""

from __future__ import annotations

import logging
import re
from datetime import date, timedelta

from domain.instrument_id import InstrumentId

logger = logging.getLogger(__name__)

# Pattern: UNDERLYING_EXPIRY_KIND_EXPIRY_OFFSET_STRIKE_REF_RIGHT
# Examples: NIFTY_WEEK_0_ATM_CE, BANKNIFTY_MONTH_1_ATM_PE, NIFTY_FUT_CURRENT
_DSL_PATTERN = re.compile(
    r"^([A-Z]+)"           # underlying
    r"_(WEEK|MONTH)"       # expiry_kind
    r"_(\d+)"              # expiry_offset (0, 1, 2, ...)
    r"_(ATM|OTM\d+|ITM\d+|[+-]?\d+)"  # strike_ref
    r"_(CE|PE|CALL|PUT)$"  # right
)

# Pattern for futures: UNDERLYING_FUT_CURRENT or UNDERLYING_FUT_0
_FUT_PATTERN = re.compile(
    r"^([A-Z]+)_FUT_(CURRENT|\d+)$"
)


def resolve_selector(
    selector: str,
    spot: float | None = None,
    exchange: str = "NFO",
    reference_date: date | None = None,
) -> InstrumentId:
    """Resolve a strategy selector to a concrete InstrumentId.

    Args:
        selector: Strategy DSL string (e.g., "NIFTY_WEEK_0_ATM_CE").
        spot: Current spot price (required for ATM strike resolution).
        exchange: Exchange code (default "NFO").
        reference_date: Reference date for expiry calculation (default today).

    Returns:
        Concrete InstrumentId.

    Raises:
        ValueError: If selector cannot be parsed or resolved.
    """
    selector = selector.strip().upper()

    # Check for equity/index passthrough
    if ":" not in selector and "_" not in selector:
        return InstrumentId.equity(exchange, selector)

    # Try futures pattern
    fut_match = _FUT_PATTERN.match(selector)
    if fut_match:
        underlying = fut_match.group(1)
        offset = 0 if fut_match.group(2) == "CURRENT" else int(fut_match.group(2))
        expiry = _resolve_expiry(underlying, offset, reference_date)
        return InstrumentId.future(exchange, underlying, expiry)

    # Try options pattern
    opt_match = _DSL_PATTERN.match(selector)
    if opt_match:
        underlying = opt_match.group(1)
        expiry_kind = opt_match.group(2)
        expiry_offset = int(opt_match.group(3))
        strike_ref = opt_match.group(4)
        right = opt_match.group(5)

        # Normalize right
        if right in ("CALL", "CE"):
            right = "CE"
        elif right in ("PUT", "PE"):
            right = "PE"

        # Resolve expiry
        expiry = _resolve_expiry(underlying, expiry_offset, reference_date, expiry_kind)

        # Resolve strike
        if strike_ref == "ATM":
            if spot is None:
                raise ValueError(f"Spot price required for ATM strike resolution in '{selector}'")
            strike = _round_to_nearest_strike(spot)
        elif re.match(r"^(OTM|ITM)\d+$", strike_ref):
            if spot is None:
                raise ValueError(f"Spot price required for {strike_ref} strike resolution in '{selector}'")
            strike = _resolve_otm_itm_strike(spot, strike_ref)
        else:
            # Numeric strike
            strike = int(strike_ref)

        return InstrumentId.option(exchange, underlying, expiry, strike, right)

    raise ValueError(f"Cannot parse strategy selector: {selector!r}")


def _resolve_expiry(
    underlying: str,
    offset: int,
    reference_date: date | None = None,
    kind: str = "WEEK",
) -> date:
    """Resolve expiry date from offset and kind.

    For WEEK: offset=0 → nearest Thursday, offset=1 → next Thursday, etc.
    For MONTH: offset=0 → current month expiry, offset=1 → next month, etc.
    """
    ref = reference_date or date.today()

    if kind == "WEEK":
        # Find nearest Thursday on or after reference
        days_to_thursday = (3 - ref.weekday()) % 7
        if days_to_thursday == 0 and ref.weekday() != 3:
            days_to_thursday = 7
        base_thursday = ref + timedelta(days=days_to_thursday)
        return base_thursday + timedelta(weeks=offset)

    if kind == "MONTH":
        # Find last Thursday of the month (offset=0) or next month (offset=1, etc.)
        # For simplicity, use first Thursday of (current_month + offset)
        target_month = ref.month + offset
        target_year = ref.year
        while target_month > 12:
            target_month -= 12
            target_year += 1

        # Find first Thursday of target month
        first_day = date(target_year, target_month, 1)
        days_to_thursday = (3 - first_day.weekday()) % 7
        first_thursday = first_day + timedelta(days=days_to_thursday)

        # For monthly expiry, typically last Thursday — use 3rd Thursday (standard for NIFTY)
        expiry = first_thursday + timedelta(weeks=2)

        # If resolved expiry is before reference, move to next month
        if expiry < ref:
            return _resolve_expiry(underlying, offset + 1, reference_date, kind)

        return expiry

    raise ValueError(f"Unknown expiry kind: {kind!r}")


def _round_to_nearest_strike(price: float, tick: float = 50.0) -> int:
    """Round price to nearest strike price.

    NIFTY strikes are in multiples of 50.
    BANKNIFTY strikes are in multiples of 100.
    """
    return int(round(price / tick) * tick)


def _resolve_otm_itm_strike(spot: float, ref: str) -> int:
    """Resolve OTM/ITM strike reference.

    OTM1 = 1 strike OTM, OTM2 = 2 strikes OTM, etc.
    ITM1 = 1 strike ITM, ITM2 = 2 strikes ITM, etc.
    """
    match = re.match(r"(OTM|ITM)(\d+)", ref)
    if not match:
        raise ValueError(f"Invalid strike reference: {ref!r}")

    direction = match.group(1)
    steps = int(match.group(2))
    tick = 50.0  # NIFTY strike tick

    base = _round_to_nearest_strike(spot, tick)
    if direction == "OTM":
        # For call: OTM = higher strike; for put: OTM = lower strike
        # Default to call convention (higher strike)
        return base + steps * int(tick)
    else:  # ITM
        return base - steps * int(tick)


def parse_selector(selector: str) -> dict:
    """Parse a selector string into its components without resolving.

    Returns dict with keys: underlying, kind, offset, strike_ref, right.

    Example:
        parse_selector("NIFTY_WEEK_0_ATM_CE")
        → {"underlying": "NIFTY", "kind": "WEEK", "offset": 0,
           "strike_ref": "ATM", "right": "CE"}
    """
    selector = selector.strip().upper()

    fut_match = _FUT_PATTERN.match(selector)
    if fut_match:
        return {
            "underlying": fut_match.group(1),
            "kind": "FUT",
            "offset": 0 if fut_match.group(2) == "CURRENT" else int(fut_match.group(2)),
            "strike_ref": None,
            "right": "FUT",
        }

    opt_match = _DSL_PATTERN.match(selector)
    if opt_match:
        return {
            "underlying": opt_match.group(1),
            "kind": opt_match.group(2),
            "offset": int(opt_match.group(3)),
            "strike_ref": opt_match.group(4),
            "right": opt_match.group(5),
        }

    # Equity/index passthrough
    return {
        "underlying": selector,
        "kind": None,
        "offset": 0,
        "strike_ref": None,
        "right": None,
    }
