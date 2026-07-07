"""Tests for brokers.common.segments — canonical segment <-> exchange mapping.

Covers:
  - segment_to_exchange: all known segment strings resolve correctly
  - exchange_to_segment: all Exchange enum members have a canonical segment
  - dhan_segment_for: Dhan wire overrides (NSE_FO→NSE_FNO, etc.)
  - Currency segments route to Exchange.CURRENCY (not MCX)
  - BSE F&O segments route to Exchange.BSE_FNO (not NFO)
"""

from __future__ import annotations

import pytest

from brokers.common.segments import (
    DHAN_SEGMENT_OVERRIDE,
    EXCHANGE_TO_SEGMENT,
    SEGMENT_TO_EXCHANGE,
    dhan_segment_for,
    exchange_to_segment,
    segment_to_exchange,
)
from brokers.domain.enums import Exchange


# ── segment_to_exchange ────────────────────────────────────────────────────────


class TestSegmentToExchange:
    """Segment strings resolve to the correct Exchange enum."""

    # Equity
    def test_nse_eq(self):
        assert segment_to_exchange("NSE_EQ") is Exchange.NSE

    def test_bse_eq(self):
        assert segment_to_exchange("BSE_EQ") is Exchange.BSE

    # NSE F&O
    def test_nse_fo(self):
        assert segment_to_exchange("NSE_FO") is Exchange.NFO

    def test_nse_fno(self):
        assert segment_to_exchange("NSE_FNO") is Exchange.NFO

    def test_nfo_short(self):
        assert segment_to_exchange("NFO") is Exchange.NFO

    # BSE F&O
    def test_bse_fo(self):
        assert segment_to_exchange("BSE_FO") is Exchange.BSE_FNO

    def test_bse_fno(self):
        assert segment_to_exchange("BSE_FNO") is Exchange.BSE_FNO

    def test_bfo_short(self):
        assert segment_to_exchange("BFO") is Exchange.BSE_FNO

    # Commodity
    def test_mcx_fo(self):
        assert segment_to_exchange("MCX_FO") is Exchange.MCX

    def test_mcx_comm(self):
        assert segment_to_exchange("MCX_COMM") is Exchange.MCX

    def test_mcx_short(self):
        assert segment_to_exchange("MCX") is Exchange.MCX

    def test_nse_com(self):
        assert segment_to_exchange("NSE_COM") is Exchange.MCX

    def test_bse_com(self):
        assert segment_to_exchange("BSE_COM") is Exchange.MCX

    # Index
    def test_nse_index(self):
        assert segment_to_exchange("NSE_INDEX") is Exchange.INDEX

    def test_bse_index(self):
        assert segment_to_exchange("BSE_INDEX") is Exchange.INDEX

    def test_idx_i(self):
        assert segment_to_exchange("IDX_I") is Exchange.INDEX

    # Currency — critical correctness: must NOT map to MCX
    def test_nse_currency(self):
        assert segment_to_exchange("NSE_CURRENCY") is Exchange.CURRENCY

    def test_bse_currency(self):
        assert segment_to_exchange("BSE_CURRENCY") is Exchange.CURRENCY

    def test_cds(self):
        assert segment_to_exchange("CDS") is Exchange.CURRENCY

    # Unknown segment falls back to default
    def test_unknown_defaults_to_nse(self):
        assert segment_to_exchange("UNKNOWN_SEGMENT") is Exchange.NSE

    def test_unknown_custom_default(self):
        assert segment_to_exchange("UNKNOWN", Exchange.BSE) is Exchange.BSE


# ── exchange_to_segment ────────────────────────────────────────────────────────


class TestExchangeToSegment:
    """Exchange enum members resolve to canonical segment strings."""

    def test_nse(self):
        assert exchange_to_segment(Exchange.NSE) == "NSE_EQ"

    def test_bse(self):
        assert exchange_to_segment(Exchange.BSE) == "BSE_EQ"

    def test_nfo(self):
        assert exchange_to_segment(Exchange.NFO) == "NSE_FO"

    def test_bse_fno(self):
        assert exchange_to_segment(Exchange.BSE_FNO) == "BSE_FO"

    def test_mcx(self):
        assert exchange_to_segment(Exchange.MCX) == "MCX_FO"

    def test_index(self):
        assert exchange_to_segment(Exchange.INDEX) == "NSE_INDEX"

    def test_currency(self):
        # Canonical (broker-agnostic) segment for currency is Upstox's wire
        # name "NSE_CD"; Dhan's "NSE_CURRENCY" form is applied via
        # dhan_segment_for (see TestDhanSegmentFor.test_currency_no_override).
        assert exchange_to_segment(Exchange.CURRENCY) == "NSE_CD"


# ── dhan_segment_for ──────────────────────────────────────────────────────────


class TestDhanSegmentFor:
    """Dhan wire segment overrides are applied correctly."""

    def test_nfo_override(self):
        """Canonical NSE_FO → Dhan NSE_FNO."""
        assert dhan_segment_for(Exchange.NFO) == "NSE_FNO"

    def test_bse_fno_override(self):
        """Canonical BSE_FO → Dhan BSE_FNO."""
        assert dhan_segment_for(Exchange.BSE_FNO) == "BSE_FNO"

    def test_mcx_override(self):
        """Canonical MCX_FO → Dhan MCX_COMM."""
        assert dhan_segment_for(Exchange.MCX) == "MCX_COMM"

    def test_index_override(self):
        """Canonical NSE_INDEX → Dhan IDX_I."""
        assert dhan_segment_for(Exchange.INDEX) == "IDX_I"

    def test_nse_no_override(self):
        """NSE_EQ has no Dhan override."""
        assert dhan_segment_for(Exchange.NSE) == "NSE_EQ"

    def test_bse_no_override(self):
        """BSE_EQ has no Dhan override."""
        assert dhan_segment_for(Exchange.BSE) == "BSE_EQ"

    def test_currency_no_override(self):
        """NSE_CURRENCY has no Dhan override."""
        assert dhan_segment_for(Exchange.CURRENCY) == "NSE_CURRENCY"


# ── Round-trip consistency ─────────────────────────────────────────────────────


class TestRoundTrip:
    """exchange → segment → exchange round-trips correctly."""

    @pytest.mark.parametrize(
        "exchange",
        [Exchange.NSE, Exchange.BSE, Exchange.NFO, Exchange.BSE_FNO, Exchange.MCX, Exchange.INDEX, Exchange.CURRENCY],
    )
    def test_canonical_round_trip(self, exchange: Exchange):
        segment = exchange_to_segment(exchange)
        assert segment_to_exchange(segment) is exchange

    @pytest.mark.parametrize(
        "exchange",
        [Exchange.NSE, Exchange.BSE, Exchange.NFO, Exchange.BSE_FNO, Exchange.MCX, Exchange.INDEX, Exchange.CURRENCY],
    )
    def test_dhan_wire_round_trip(self, exchange: Exchange):
        """Dhan wire segment → Exchange → Dhan wire segment."""
        wire = dhan_segment_for(exchange)
        resolved = segment_to_exchange(wire)
        assert resolved is exchange
