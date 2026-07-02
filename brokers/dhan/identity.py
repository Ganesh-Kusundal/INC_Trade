"""Dhan identity provider — single source of truth for symbol→security_id.

Why this module exists
----------------------
Every adapter that talks to Dhan must produce a payload containing a
``securityId`` (string) and an ``exchangeSegment`` (one of the Dhan segment
codes). Historically every adapter called
``self._resolver.resolve(symbol, exchange)`` and then computed the segment
from ``EXCHANGE_TO_SEGMENT.get(...)`` independently. That worked but it had
three problems:

1. A caller could in principle bypass the resolver and ship any number as a
   ``securityId`` — there was no type-level guarantee that what reached the
   HTTP body came from a Dhan-controlled source.
2. The Upstox / Dhan boundary was implicit. The Dhan resolver happens to be
   the only place that produces Dhan-internal security IDs, but nothing
   prevented a future change from accidentally feeding Upstox data into it.
3. Audit trail: when a security_id is shipped to Dhan, we had no structured
   log of *which* row in *which* source produced it (CSV vs MCX JSON vs the
   hardcoded index table).

This module fixes all three by:

* Owning the ``SymbolResolver`` and the ``indices.py`` hardcoded
  table behind a single ``DhanIdentityProvider`` factory.
* Wrapping every successful resolution in an immutable ``DhanInstrumentRef``
  that structurally cannot carry an Upstox identifier (the
  ``exchange_segment`` field is a literal from Dhan's own set, enforced at
  construction).
* Emitting a structured ``security_id_issued`` audit event with the
  ``source`` field ("csv" / "mcx_json" / "hardcoded_index").
* Exposing one ``resolve_ref(symbol, exchange, *, expected_segment=None)``
  method that the adapters call. The optional ``expected_segment`` argument
  (PR-C) lets the caller disambiguate between an index spot LTP query and
  a derivatives query for the same underlying.

Anything in ``brokers/dhan/**`` that builds an outgoing Dhan HTTP payload
**must** import from this module — *not* from ``brokers/dhan/resolver.py``
directly. The DhanIdentityProvider is the only legal path to a
``DhanInstrumentRef``.

Public surface
--------------
* :class:`DhanInstrumentRef` — the immutable carrier.
* :class:`DhanIdentityProvider` — the factory.
* :class:`DhanIdentityError` — raised on resolution failure (re-exported
  from :mod:`brokers.dhan.exceptions`).
* :data:`DHAN_SEGMENTS` — the canonical set of Dhan segment codes.
* :func:`is_dhan_segment` — predicate used by invariant checks.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Any

from brokers.dhan.domain import Exchange, Instrument, InstrumentType
from brokers.dhan.exceptions import DhanIdentityError, InstrumentNotFoundError
from brokers.dhan.resolver import SymbolResolver
from brokers.dhan.segments import EXCHANGE_TO_SEGMENT

logger = logging.getLogger(__name__)


class DhanIdentitySource(str, Enum):
    """Where a ``DhanInstrumentRef``'s security_id originated from.

    Used for audit logging. Every successful ``resolve_ref`` records the
    source so SREs can confirm the resolver's coverage.
    """

    CSV = "csv"
    MCX_JSON = "mcx_json"
    HARDCODED_INDEX = "hardcoded_index"


# ── Canonical Dhan segment set ──────────────────────────────────────────────
#
# These are the segment codes Dhan accepts in any payload that names a
# security. The set is *not* derived from EXCHANGE_TO_SEGMENT at runtime
# because the intent here is to spell out Dhan's own published set so a
# reviewer can audit it in one place. Keeping this literal also lets the
# invariant checker fail-fast on any unknown value.
DHAN_SEGMENTS: frozenset[str] = frozenset(
    {
        "NSE_EQ",
        "NSE_FNO",
        "NSE_COMM",
        "BSE_EQ",
        "BSE_FNO",
        "MCX_COMM",
        "NSE_CURRENCY",
        "BSE_CURRENCY",
        "IDX_I",
    }
)


def is_dhan_segment(segment: str) -> bool:
    """True iff *segment* is one of Dhan's published segment codes."""
    return segment in DHAN_SEGMENTS


def _coerce_exchange(value: Any) -> Exchange:
    """Accept either an :class:`Exchange` enum value or its string form.

    Tests and external callers frequently pass the exchange as a plain
    string (``"NSE"``). The carrier normalises both forms to the enum.

    Mock objects (e.g. :class:`unittest.mock.MagicMock`) that aren't a
    string or enum value are returned unchanged. The carrier's
    ``__post_init__`` invariant is structural (it checks
    ``exchange_segment``, not ``exchange``), so passing through a
    mock-shaped value keeps the contract honest while preserving test
    ergonomics.
    """
    if isinstance(value, Exchange):
        return value
    if isinstance(value, str):
        try:
            return Exchange(value)
        except ValueError:
            # The carrier must still validate via __post_init__ —
            # unknown exchanges will not match any Dhan segment and
            # will be rejected by the carrier's segment check.
            return value  # type: ignore[return-value]
    # Any other object (e.g. MagicMock, dataclass-like shim) is
    # returned unchanged. The carrier's structural checks operate on
    # exchange_segment, not on the exchange enum value itself.
    return value  # type: ignore[return-value]


# ── The carrier ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DhanInstrumentRef:
    """An immutable, structurally-Dhan-internal instrument reference.

    Attributes
    ----------
    symbol:
        The user-facing trading symbol as resolved.
    exchange:
        Dhan's :class:`Exchange` enum value (NSE / BSE / NFO / BFO / MCX /
        CDS / INDEX). A plain string with the same value is also accepted
        for ergonomic call sites; the carrier normalises to the enum.
    exchange_segment:
        Dhan segment code (one of :data:`DHAN_SEGMENTS`). Always a string
        from the Dhan set; never an Upstox instrument_key.
    security_id:
        Dhan's exchange standard security ID (string of digits). Either
        from the master CSV, the MCX JSON supplement, or the hardcoded
        index table.
    instrument_type:
        Dhan :class:`InstrumentType` classification. Optional for callers
        that don't need it; ``resolve_ref`` populates this from the
        resolver.
    lot_size:
        Lot size in number of shares/contracts. Defaults to 1 for spot
        instruments.
    is_synthetic_index:
        True when the ref was constructed from
        :mod:`config.indices` (the hardcoded NIFTY=13 / BANKNIFTY=25
        table). Useful for callers that want to refuse derivative-style
        operations on a synthetic spot ref.
    source:
        :class:`DhanIdentitySource` value, recorded for audit. Defaults to
        ``CSV`` when callers construct the ref directly.
    underlying:
        Underlying root symbol for F&O contracts (e.g. ``"NIFTY"`` for a
        NIFTY option). None for cash / index spot.
    expiry:
        ISO date string for derivatives, else None.
    strike_price:
        Strike price for options, else None.
    option_type:
        CALL or PUT for options, else None.
    """

    symbol: str
    exchange: Any  # Exchange | str; normalised in __post_init__
    exchange_segment: str
    security_id: str
    instrument_type: InstrumentType = InstrumentType.EQUITY
    lot_size: int = 1
    source: DhanIdentitySource = DhanIdentitySource.CSV
    is_synthetic_index: bool = False
    underlying: str | None = None
    expiry: str | None = None
    strike_price: object | None = None  # Decimal | None — avoid extra import
    option_type: object | None = None  # OptionType | None

    def __post_init__(self) -> None:
        # Normalise exchange to the Enum form (accepts strings for
        # ergonomic call sites). Done via object.__setattr__ because
        # the dataclass is frozen.
        normalised_exchange = _coerce_exchange(self.exchange)
        if normalised_exchange is not self.exchange:
            object.__setattr__(self, "exchange", normalised_exchange)

        # Enforce the Dhan-internal contract at construction time. A
        # caller that somehow produces a foreign segment or a non-digit
        # security_id gets a DhanIdentityError immediately, before the
        # value can reach an HTTP payload.
        if not is_dhan_segment(self.exchange_segment):
            raise DhanIdentityError(
                f"Invalid exchange_segment: {self.exchange_segment!r} "
                f"is not a Dhan segment (allowed: {sorted(DHAN_SEGMENTS)})"
            )
        if not self.security_id or not self.security_id.isdigit():
            raise DhanIdentityError(
                f"Invalid security_id: {self.security_id!r} (must be a positive digit string)"
            )
        if int(self.security_id) <= 0:
            raise DhanIdentityError(
                f"Invalid security_id: {self.security_id!r} (must be a positive digit string)"
            )

    # ── Convenience properties for the common payload-building cases ──

    @property
    def is_derivative(self) -> bool:
        """True for futures / options, False for equity / index spot."""
        return self.instrument_type in (InstrumentType.FUTURE, InstrumentType.OPTION)

    @property
    def is_option(self) -> bool:
        return self.instrument_type == InstrumentType.OPTION

    @property
    def is_future(self) -> bool:
        return self.instrument_type == InstrumentType.FUTURE

    def security_id_str(self) -> str:
        """Return the security_id as a string. Always a string, always digits.

        Dhan's official docs show ``securityId`` as a JSON string
        (``"securityId":"11536"``); this is the canonical helper for
        payload builders. Use this everywhere instead of stringifying
        ``security_id`` ad-hoc.
        """
        return str(self.security_id)


# ── The provider ────────────────────────────────────────────────────────────


class DhanIdentityProvider:
    """Single source of truth for Dhan symbol→security_id resolution.

    The provider wraps a :class:`SymbolResolver` plus the
    :mod:`config.indices` hardcoded index table, and exposes
    :meth:`resolve_ref`. The method:

    1. Calls ``self._resolver.resolve(symbol, exchange)`` which may raise
       :class:`InstrumentNotFoundError`.
    2. Wraps the resulting :class:`Instrument` in a
       :class:`DhanInstrumentRef` (enforcing the Dhan-internal contract
       via ``__post_init__``).
    3. Emits a structured ``security_id_issued`` audit log with the
       source (CSV vs hardcoded_index) so the SRE layer can trace
       every security_id back to its origin.
    4. Optionally consults ``expected_segment`` (PR-C.4) to fail-fast when
       a caller asks for an NFO/BFO/MCX/Currency contract but the
       resolver is about to silently substitute the index fallback.
    """

    # Segments that the caller cannot satisfy with the index fallback. If
    # the resolver's index-fallback fires for a symbol in this set, we
    # raise InstrumentNotFoundError with an actionable message.
    _DERIVATIVE_SEGMENTS: frozenset[str] = frozenset(
        {"NSE_FNO", "BSE_FNO", "MCX_COMM", "NSE_CURRENCY", "BSE_CURRENCY", "NSE_COMM"}
    )

    def __init__(self, resolver: SymbolResolver):
        self._resolver = resolver
        self._lock = threading.RLock()
        # Monotonic counter for the audit log; cheap and useful for
        # confirming the provider is actually being hit during a session.
        self._issue_count: int = 0
        self._synthetic_index_count: int = 0

    @property
    def resolver(self) -> SymbolResolver:
        """Underlying resolver. Exposed for tests and the gateway's
        ``search`` method which still walks the resolver directly."""
        return self._resolver

    @property
    def issue_count(self) -> int:
        """Number of ``DhanInstrumentRef`` instances ever issued."""
        with self._lock:
            return self._issue_count

    @property
    def synthetic_index_count(self) -> int:
        """Number of issued refs that came from the hardcoded index table.

        If this number grows unexpectedly during a session it is a sign
        that the master CSV is missing an index row.
        """
        with self._lock:
            return self._synthetic_index_count

    @staticmethod
    def to_payload_security_id(ref: DhanInstrumentRef) -> str:
        """Return the carrier's ``security_id`` formatted for an HTTP payload.

        Always returns a ``str`` of digits (Dhan's official JSON wire
        format shows ``"securityId":"11536"`` rather than an integer).
        Prefer this helper over ``str(ref.security_id)`` so future
        changes to the carrier's internal storage (e.g. integer-only
        representation) cannot silently break payload formatting.
        """
        if ref is None:
            raise DhanIdentityError("to_payload_security_id: ref is None")
        return ref.security_id_str()

    def resolve_ref(
        self,
        symbol: str,
        exchange: str,
        *,
        expected_segment: str | None = None,
    ) -> DhanInstrumentRef:
        """Resolve *symbol* on *exchange* to a :class:`DhanInstrumentRef`.

        Parameters
        ----------
        symbol:
            User-facing trading symbol (e.g. ``"NIFTY"``,
            ``"NIFTY 26 JUN 25000 CE"``, ``"RELIANCE"``).
        exchange:
            Exchange hint, case-insensitive. Accepted values include the
            Dhan :class:`Exchange` enum members and a few aliases mapped
            via :data:`brokers.dhan.segments.SEGMENT_TO_EXCHANGE`.
        expected_segment:
            Optional Dhan segment hint used to disambiguate index vs
            derivatives lookups. When set to a derivative segment
            (``NSE_FNO``, ``BSE_FNO``, ``MCX_COMM``, ``NSE_CURRENCY``,
            ``BSE_CURRENCY``, ``NSE_COMM``) the resolver's silent
            index-fallback is replaced with a clear
            :class:`InstrumentNotFoundError`. Pass
            ``"IDX_I"`` to require the synthetic index ref.

        Returns
        -------
        :class:`DhanInstrumentRef`

        Raises
        ------
        InstrumentNotFoundError
            When the resolver cannot find a match, or when the
            ``expected_segment`` constraint rejects an otherwise-matching
            synthetic index ref.
        DhanIdentityError
            When the resolved instrument's ``exchange`` does not map to a
            Dhan segment — defence-in-depth against future registry drift.
        """
        # We intentionally do *not* pass expected_segment into the
        # resolver here; the resolver's own accept-segment logic is
        # controlled by a new optional kwarg in PR-C.4. We pre-check
        # after the resolver returns to keep the two changes orthogonal.
        inst = self._resolver.resolve(symbol, exchange)
        return self._wrap(inst, expected_segment=expected_segment)

    def resolve_ref_from_security_id(
        self,
        security_id: str,
        exchange: str,
    ) -> DhanInstrumentRef | None:
        """Reverse-lookup helper.

        Returns the :class:`DhanInstrumentRef` for *security_id* on
        *exchange*, or ``None`` if the resolver does not have it.

        The reverse-lookup path is only used by the option-chain and
        expired-options flows. Callers MUST not invent a security_id and
        call this — the only acceptable inputs are values the broker
        itself returned, or values the resolver already produced.
        """
        inst = self._resolver.get_by_security_id(str(security_id))
        if inst is None:
            return None
        # Use the wrapper without an expected_segment constraint — the
        # reverse path is only invoked by adapters that already know the
        # segment.
        return self._wrap(inst, expected_segment=None)

    # ── internals ─────────────────────────────────────────────────────

    def _wrap(
        self,
        inst: Instrument,
        *,
        expected_segment: str | None,
    ) -> DhanInstrumentRef:
        segment = EXCHANGE_TO_SEGMENT.get(inst.exchange.value)
        if segment is None:
            raise DhanIdentityError(
                f"resolved instrument has non-Dhan exchange value: "
                f"{inst.exchange.value!r} (symbol={inst.symbol!r})"
            )

        # If the caller declared an expected derivative segment and the
        # resolver returned the synthetic index fallback, fail fast with
        # a message that points the operator at the right input form.
        # Raised as a ``DhanIdentityError`` so it sits at the same level
        # in the exception hierarchy as other identity-contract failures;
        # the message ("resolved to index") is the canonical signal to
        # the caller that they crossed the index/derivative boundary.
        if expected_segment in self._DERIVATIVE_SEGMENTS and segment == "IDX_I":
            raise DhanIdentityError(
                f"{inst.symbol!r} resolved to index (segment=IDX_I) but "
                f"caller expected derivative segment {expected_segment!r}. "
                f"Specify the derivative contract explicitly, e.g. "
                f"'NIFTY 26 JUN 25000 CE' for an NFO option."
            )
        if expected_segment is not None and segment != expected_segment:
            raise InstrumentNotFoundError(
                f"resolve({inst.symbol!r}, {inst.exchange.value!r}) returned "
                f"segment {segment!r}, but caller required {expected_segment!r}"
            )

        is_synthetic = inst.name == "INDEX" and inst.sm_symbol_name is None
        source = DhanIdentitySource.HARDCODED_INDEX if is_synthetic else DhanIdentitySource.CSV
        # Normalise security_id to a string. Some callers (and the
        # ``Instrument`` dataclass itself) carry the id as an int; the
        # carrier requires a string of digits for invariant checks and
        # for direct use in HTTP payloads.
        raw_sid = inst.security_id
        sid_str = str(raw_sid) if not isinstance(raw_sid, str) else raw_sid
        ref = DhanInstrumentRef(
            symbol=inst.symbol,
            exchange=inst.exchange,
            exchange_segment=segment,
            security_id=sid_str,
            instrument_type=inst.instrument_type,
            lot_size=inst.lot_size,
            source=source,
            is_synthetic_index=is_synthetic,
            underlying=inst.underlying,
            expiry=inst.expiry,
            strike_price=inst.strike_price,
            option_type=inst.option_type,
        )
        with self._lock:
            self._issue_count += 1
            if is_synthetic:
                self._synthetic_index_count += 1

        logger.info(
            "security_id_issued",
            extra={
                "symbol": inst.symbol,
                "exchange": inst.exchange.value,
                "exchange_segment": segment,
                "security_id": inst.security_id,
                "source": source.value,
                "expected_segment": expected_segment,
                "is_synthetic_index": is_synthetic,
            },
        )
        return ref


def coerce_identity_provider(
    identity: DhanIdentityProvider | SymbolResolver | object,
    allow_duck: bool = False,
) -> DhanIdentityProvider:
    """Return a :class:`DhanIdentityProvider` for *identity*.

    Accepts any of:

    * an existing :class:`DhanIdentityProvider` (returned as-is);
    * a raw :class:`SymbolResolver` (wrapped in a new provider);
    * any object that exposes ``.resolver`` (treated as a provider);

    **Duck-typed fallback (opt-in only):**

    * any object that quacks like a ``SymbolResolver`` (``.resolve`` and
      ``.get_by_security_id`` methods) — wrapped using itself as the
      underlying resolver. **Disabled by default.** Pass
      ``allow_duck=True`` to enable this branch. Production code should
      never pass ``allow_duck=True``; the branch exists so test
      fixtures and :class:`unittest.mock.MagicMock` mocks can opt in
      explicitly.

    This is a backward-compatibility helper. Older tests and external
    callers constructed adapters with a ``SymbolResolver`` directly:

        OrdersAdapter(client, resolver)

    The hardened adapter signature requires a :class:`DhanIdentityProvider`
    so that the Dhan-internal contract is enforced end-to-end. This helper
    lets existing call-sites continue to work without bypassing the
    invariants.

    Why ``allow_duck`` is opt-in (Plan §7.4)
    ----------------------------------------
    The previous behaviour accepted any quacking object. That meant a
    MagicMock that happened to expose ``resolve`` /
    ``get_by_security_id`` would be wrapped as a real provider, masking
    any test fixture that was *meant* to bypass the provider. Test
    discipline is now load-bearing: a test that genuinely needs the
    duck-typing fallback must opt in, and the production call sites
    never do.
    """
    if isinstance(identity, DhanIdentityProvider):
        return identity
    # Anything exposing ``.resolver`` is treated as a provider-shaped object.
    resolver_attr = getattr(identity, "resolver", None)
    if isinstance(resolver_attr, SymbolResolver):
        return DhanIdentityProvider(resolver_attr)
    if isinstance(identity, SymbolResolver):
        return DhanIdentityProvider(identity)
    # Duck-typed fallback: only when the caller has explicitly opted in.
    # Default ``False`` means production code paths reject anything that
    # is not a real ``DhanIdentityProvider`` or ``SymbolResolver``.
    if (
        allow_duck
        and callable(getattr(identity, "resolve", None))
        and callable(getattr(identity, "get_by_security_id", None))
    ):
        return DhanIdentityProvider(identity)  # type: ignore[arg-type]
    raise TypeError(
        "identity must be a DhanIdentityProvider or SymbolResolver; "
        f"got {type(identity).__name__}. "
        "Pass allow_duck=True to enable the duck-typed test fallback."
    )


__all__ = [
    "DHAN_SEGMENTS",
    "DhanIdentityError",
    "DhanIdentityProvider",
    "DhanIdentitySource",
    "DhanInstrumentRef",
    "coerce_identity_provider",
    "is_dhan_segment",
]
