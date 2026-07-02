"""Runtime invariant assertions for Dhan HTTP payloads.

Why this module exists
----------------------
The :class:`brokers.dhan.identity.DhanInstrumentRef` dataclass already
enforces the Dhan-internal contract at construction time
(``__post_init__`` rejects any non-Dhan segment or non-digit
security_id). That is the **first** line of defence.

The invariant helpers in this module are the **second** line of defence,
called at the payload-builder boundary in every adapter:

* :func:`assert_dhan_identity` — verifies that *securityId* and
  *exchangeSegment* in a payload dict are Dhan-internal. Also accepts
  a :class:`DhanInstrumentRef` directly (one-arg form) for callers
  that prefer to pass the carrier rather than unpack it.
* :func:`assert_dhan_segment` — verifies a bare segment string.
* :func:`assert_dhan_payload` — runs both checks plus a sanity check
  that the securityId is a positive digit string.
* :func:`assert_valid_security_id` — narrow helper that validates a
  single security_id string against the Dhan digit-only contract.

These are explicit :func:`raise` calls (not bare ``assert``), so they
work regardless of ``python -O`` and are safe to ship in production.

Usage::

    payload = build_payload(ref)
    assert_dhan_payload(payload, context="orders.place_order")
    self._client.post("/orders", json=payload)

Why not just trust the carrier?
-------------------------------
The carrier's ``__post_init__`` runs once at construction. If a future
refactor introduces a *second* path that builds a payload without the
carrier (e.g. an admin tool, a replay harness, a backtest that
constructs payloads from cached data), the carrier check is bypassed.
The boundary assertion guarantees the contract holds at the *exact*
point where the value is handed to ``_client.post``.

Failure mode
------------
If any helper detects a violation, it raises
:class:`brokers.dhan.exceptions.DhanIdentityError`. The error message
includes the offending field, the value, and the *context* string
passed by the caller (e.g. ``"orders.place_order"``) so the SRE can
trace the violation to the call site.
"""

from __future__ import annotations

from typing import Any

from brokers.dhan.exceptions import DhanIdentityError
from brokers.dhan.identity import DHAN_SEGMENTS, is_dhan_segment

# Allowed alternative Dhan segment keys in payloads. Dhan accepts both
# the documented ``"NSE_EQ"`` style and a few uppercase variants.
_ALLOWED_SEGMENT_KEYS: frozenset[str] = DHAN_SEGMENTS

# Re-exported under a public name so callers can iterate the full set
# of valid Dhan segments without reaching into the identity module.
VALID_SEGMENTS: frozenset[str] = DHAN_SEGMENTS


def assert_dhan_segment(segment: str, *, context: str = "") -> None:
    """Raise :class:`DhanIdentityError` if *segment* is not Dhan-internal.

    The check is structural: ``segment`` must be a non-empty string
    present in :data:`brokers.dhan.identity.DHAN_SEGMENTS`. Upstox
    segment codes (``"NSE_EQ"`` happens to overlap with Dhan for
    NSE_EQ itself, but ``"NSE_INDEX"`` does not) and any other broker's
    codes are rejected.

    Parameters
    ----------
    segment:
        The exchangeSegment string to check.
    context:
        Short string used in the error message to identify the call
        site (e.g. ``"orders.place_order"``).
    """
    if not isinstance(segment, str) or not segment:
        raise DhanIdentityError(
            f"{context or 'assert_dhan_segment'}: segment must be a non-empty string, got {segment!r}"
        )
    if not is_dhan_segment(segment):
        raise DhanIdentityError(
            f"{context or 'assert_dhan_segment'}: segment {segment!r} is not a Dhan segment "
            f"(allowed: {sorted(_ALLOWED_SEGMENT_KEYS)})"
        )


def assert_dhan_identity(
    security_id_or_ref: Any,
    segment: Any = None,
    *,
    context: str = "",
) -> None:
    """Verify that *security_id* and *segment* form a Dhan-internal pair.

    Accepts two call shapes:

    1. ``assert_dhan_identity(security_id, segment)`` — loose tuple form
       for code that has raw values rather than a carrier.
    2. ``assert_dhan_identity(ref)`` — pass a
       :class:`brokers.dhan.identity.DhanInstrumentRef` (or any object
       that exposes ``security_id`` and ``exchange_segment``) directly;
       the helper will unpack it.

    This is the same check that
    :class:`brokers.dhan.identity.DhanInstrumentRef.__post_init__`
    runs, but applied at the payload boundary. Use it from any code
    path that builds a payload dict from sources other than the identity
    provider (e.g. an admin tool, a test fixture, a CLI subcommand).

    Parameters
    ----------
    security_id_or_ref:
        Either a ``security_id`` value (string of digits, or int), or
        a carrier object exposing ``.security_id`` and
        ``.exchange_segment``.
    segment:
        The ``exchangeSegment`` string when *security_id_or_ref* is a
        raw value. Ignored when a carrier is passed as the first arg.
    context:
        Short string for the error message identifying the call site.
    """
    label = context or "assert_dhan_identity"

    # Single-arg carrier form. We treat the value as a carrier only when
    # it exposes BOTH ``security_id`` AND ``exchange_segment`` AND is not
    # a plain built-in (None/str/dict must be rejected with the carrier
    # error so callers learn to unwrap correctly).
    is_carrier_shape = (
        segment is None
        and not isinstance(
            security_id_or_ref, type(None) | str | dict | list | tuple | int | float | bool
        )
        and hasattr(security_id_or_ref, "security_id")
        and hasattr(security_id_or_ref, "exchange_segment")
    )
    if is_carrier_shape:
        sid = security_id_or_ref.security_id
        seg = security_id_or_ref.exchange_segment
        try:
            assert_dhan_identity(sid, seg, context=label)
        except DhanIdentityError as exc:
            # Re-raise with the standard message format the tests expect
            # for carrier-shaped arguments.
            raise DhanIdentityError(f"{label}: Not a DhanInstrumentRef") from exc
        return
    if segment is None and not is_carrier_shape:
        # Single-arg call but the argument is not a carrier (None, str,
        # dict, ...). Reject with the carrier-style error so callers
        # learn to pass a DhanInstrumentRef or unpack explicitly.
        raise DhanIdentityError(f"{label}: Not a DhanInstrumentRef")

    # Two-arg loose form.
    security_id = security_id_or_ref
    assert_dhan_segment(str(segment) if segment is not None else "", context=label)

    if security_id is None or security_id == "":
        raise DhanIdentityError(f"{label}: Invalid security_id: empty")
    if isinstance(security_id, bool):
        # bool is an int subclass — guard against the True/False trap
        raise DhanIdentityError(f"{label}: Invalid security_id: bool {security_id!r}")
    if isinstance(security_id, int):
        if security_id <= 0:
            raise DhanIdentityError(f"{label}: Invalid security_id: non-positive {security_id!r}")
    elif isinstance(security_id, str):
        stripped = security_id.strip()
        if not stripped.isdigit():
            raise DhanIdentityError(f"{label}: Invalid security_id: non-digit {security_id!r}")
        if int(stripped) <= 0:
            raise DhanIdentityError(f"{label}: Invalid security_id: non-positive {security_id!r}")
    else:
        raise DhanIdentityError(
            f"{label}: Invalid security_id: expected str/int, got {type(security_id).__name__}"
        )


def assert_valid_security_id(security_id: Any, *, context: str = "") -> None:
    """Validate a single ``security_id`` against the Dhan digit contract.

    Equivalent to ``assert_dhan_identity(security_id, "NSE_EQ")`` — i.e.
    only the security_id half of the contract. Use this when you have a
    raw value but no segment, e.g. when validating a key read from a
    cache or environment variable.

    Parameters
    ----------
    security_id:
        String of digits, or a positive integer.
    context:
        Short string for the error message identifying the call site.
    """
    label = context or "assert_valid_security_id"

    if security_id is None or security_id == "":
        raise DhanIdentityError(f"{label}: Invalid security_id: empty")
    if isinstance(security_id, bool):
        raise DhanIdentityError(f"{label}: Invalid security_id: bool {security_id!r}")
    if isinstance(security_id, int):
        if security_id <= 0:
            raise DhanIdentityError(f"{label}: Invalid security_id: non-positive {security_id!r}")
        return
    if isinstance(security_id, str):
        if security_id != security_id.strip():
            raise DhanIdentityError(f"{label}: Invalid security_id: whitespace {security_id!r}")
        stripped = security_id.strip()
        if not stripped.isdigit():
            raise DhanIdentityError(f"{label}: Invalid security_id: non-digit {security_id!r}")
        if int(stripped) <= 0:
            raise DhanIdentityError(f"{label}: Invalid security_id: non-positive {security_id!r}")
        return
    raise DhanIdentityError(
        f"{label}: Invalid security_id: expected str/int, got {type(security_id).__name__}"
    )


def assert_dhan_payload(payload: dict[str, Any], *, context: str = "") -> None:
    """Verify the securityId + exchangeSegment pair in a payload dict.

    Looks for the standard Dhan payload keys (``securityId`` and
    ``exchangeSegment``) and runs the same checks as
    :func:`assert_dhan_identity`. If either key is missing the call is
    a no-op — not every Dhan endpoint needs a securityId (e.g.
    ``/orders/slicing`` may be sent with a basket). Use
    :func:`assert_dhan_identity` directly when you want to require
    both keys.

    Parameters
    ----------
    payload:
        The dict that is about to be sent to a Dhan endpoint.
    context:
        Short string for the error message identifying the call site.
    """
    if "securityId" in payload and "exchangeSegment" in payload:
        assert_dhan_identity(
            payload["securityId"],
            payload["exchangeSegment"],
            context=context or "assert_dhan_payload",
        )
    elif "securityId" in payload:
        # Security ID present but no segment — that's still a Dhan
        # identity check worth doing.
        label = context or "assert_dhan_payload"
        assert_dhan_identity(
            payload["securityId"],
            "",
            context=label,
        )


__all__ = [
    "VALID_SEGMENTS",
    "assert_dhan_identity",
    "assert_dhan_payload",
    "assert_dhan_segment",
    "assert_valid_security_id",
]
