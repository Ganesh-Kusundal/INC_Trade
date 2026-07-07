"""Canonical segment <-> exchange mapping for all brokers.

Single source of truth for translating between the domain :class:`Exchange`
enum and the textual *segment* strings brokers use on the wire.

Background / why this module exists
-----------------------------------
The translation was previously duplicated 4-5x across the Dhan and Upstox
brokers (provider, mapper, resolver, streaming payloads), with drift:

* Dhan and Upstox use *different wire segment vocabularies* for the same
  logical exchange.  Dhan emits ``NSE_FNO`` / ``MCX_COMM`` / ``IDX_I`` while
  Upstox emits ``NSE_FO`` / ``MCX_FO`` / ``NSE_INDEX``.  These are broker
  wire contracts and are preserved verbatim (see :data:`DHAN_SEGMENT_OVERRIDE`
  and :func:`dhan_segment_for`).
* The *reverse* direction (segment -> exchange) is broker-agnostic: a given
  segment string unambiguously identifies an exchange regardless of which
  broker emitted it.  That direction is fully unified here.

Inconsistency resolved
----------------------
``NSE_CURRENCY`` / ``BSE_CURRENCY`` segment strings previously mapped to
``Exchange.NFO`` in one place and ``Exchange.MCX`` in others.  The domain
enum now has a dedicated ``Exchange.CURRENCY`` member, and both brokers
route currency segments to it.  ``BSE_FNO`` / ``BSE_FO`` similarly map
to ``Exchange.BSE_FNO``.
"""

from __future__ import annotations

from brokers.domain.enums import Exchange

# ── Canonical (broker-agnostic) exchange -> segment ────────────────────────────
# Preferred vocabulary, matching Upstox's wire names.  Dhan overrides the three
# segments it spells differently via DHAN_SEGMENT_OVERRIDE.
EXCHANGE_TO_SEGMENT: dict[Exchange, str] = {
    Exchange.NSE: "NSE_EQ",
    Exchange.BSE: "BSE_EQ",
    Exchange.NFO: "NSE_FO",
    Exchange.BSE_FNO: "BSE_FO",
    Exchange.MCX: "MCX_FO",
    Exchange.INDEX: "NSE_INDEX",
    Exchange.CURRENCY: "NSE_CD",
}

# ── Segment -> exchange (union of every string either broker emits) ────────────
# This is the de-duplicated replacement for the per-broker
# _SEGMENT_TO_EXCHANGE / _WIRE_TO_EXCHANGE / _UPSTOX_SEGMENT_TO_EXCHANGE maps.
SEGMENT_TO_EXCHANGE: dict[str, Exchange] = {
    # Equity
    "NSE_EQ": Exchange.NSE,
    "BSE_EQ": Exchange.BSE,
    # F&O - NSE
    "NSE_FO": Exchange.NFO,
    "NSE_FNO": Exchange.NFO,
    "NFO": Exchange.NFO,
    # F&O - BSE
    "BSE_FO": Exchange.BSE_FNO,
    "BSE_FNO": Exchange.BSE_FNO,
    "BFO": Exchange.BSE_FNO,
    # Commodity - MCX
    "MCX_FO": Exchange.MCX,
    "MCX_COMM": Exchange.MCX,
    "MCX": Exchange.MCX,
    "NSE_COM": Exchange.MCX,
    "BSE_COM": Exchange.MCX,
    # Index
    "NSE_INDEX": Exchange.INDEX,
    "BSE_INDEX": Exchange.INDEX,
    "IDX_I": Exchange.INDEX,
    # Currency — Upstox wire names (NSE_CD / BSE_CD)
    "NSE_CD": Exchange.CURRENCY,
    "BSE_CD": Exchange.CURRENCY,
    # Dhan wire names (NSE_CURRENCY / BSE_CURRENCY) — kept for reverse mapping
    "NSE_CURRENCY": Exchange.CURRENCY,
    "BSE_CURRENCY": Exchange.CURRENCY,
    "CDS": Exchange.CURRENCY,
}

# Dhan spells several segments differently on the wire.  Canonical -> Dhan wire.
DHAN_SEGMENT_OVERRIDE: dict[str, str] = {
    "NSE_FO": "NSE_FNO",
    "BSE_FO": "BSE_FNO",
    "MCX_FO": "MCX_COMM",
    "NSE_INDEX": "IDX_I",
    "NSE_CD": "NSE_CURRENCY",
    "BSE_CD": "BSE_CURRENCY",
}


def exchange_to_segment(exchange: Exchange) -> str:
    """Return the canonical segment name for an exchange.

    This is broker-agnostic and matches Upstox's wire vocabulary.  Use
    :func:`dhan_segment_for` when building Dhan requests/keys.
    """
    return EXCHANGE_TO_SEGMENT.get(exchange, "NSE_EQ")


def segment_to_exchange(segment: str, default: Exchange = Exchange.NSE) -> Exchange:
    """Translate any known segment string to its domain exchange."""
    return SEGMENT_TO_EXCHANGE.get(segment, default)


def dhan_segment_for(exchange: Exchange) -> str:
    """Dhan wire segment for an exchange (canonical form + Dhan overrides)."""
    canonical = exchange_to_segment(exchange)
    return DHAN_SEGMENT_OVERRIDE.get(canonical, canonical)


__all__ = [
    "EXCHANGE_TO_SEGMENT",
    "SEGMENT_TO_EXCHANGE",
    "DHAN_SEGMENT_OVERRIDE",
    "exchange_to_segment",
    "segment_to_exchange",
    "dhan_segment_for",
]
