"""Dhan payload invariants — defence-in-depth boundary checks.

Every HTTP call to Dhan must pass through assert_valid_dhan_payload before
the request is sent. This catches bugs where a symbol string or invalid
segment code leaks into the wire payload.
"""

from __future__ import annotations

from typing import Any

from brokers.adapters.dhan.config import DHAN_SEGMENTS


def assert_valid_dhan_payload(payload: dict[str, Any], *, context: str = "") -> None:
    """Verify securityId + exchangeSegment before HTTP call.

    Raises ValueError if:
    - securityId is present but not a positive digit string
    - exchangeSegment is present but not in DHAN_SEGMENTS
    - market data dict values contain non-numeric security IDs

    This is a hard raise (not assert), works with python -O.
    """
    tag = f" [{context}]" if context else ""

    sid = payload.get("securityId")
    if sid is not None:
        sid_str = str(sid)
        if not sid_str.isdigit() or int(sid_str) <= 0:
            raise ValueError(
                f"Invalid securityId{tag}: {sid!r}. Must be a positive digit string."
            )

    segment = payload.get("exchangeSegment")
    if segment is not None:
        if segment not in DHAN_SEGMENTS:
            raise ValueError(
                f"Invalid exchangeSegment{tag}: {segment!r}. "
                f"Must be one of {sorted(DHAN_SEGMENTS)}."
            )

    for key, value in payload.items():
        if key in ("securityId", "exchangeSegment"):
            continue
        if key in DHAN_SEGMENTS and isinstance(value, list):
            for item in value:
                if isinstance(item, int) and item > 0:
                    continue
                if isinstance(item, str) and item.isdigit() and int(item) > 0:
                    continue
                raise ValueError(
                    f"Invalid security_id in market data payload{tag}: "
                    f"segment={key}, value={item!r}. Must be int or digit string."
                )
