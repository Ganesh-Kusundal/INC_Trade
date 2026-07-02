"""Live integration tests for Dhan symbol mapping using real CSV.

This test loads the real, live scrip master from Dhan (via cache or fresh download)
and verifies that bidirectional mapping works correctly for a random sample of
instruments from each segment.
"""

from __future__ import annotations

import random

import pytest

from brokers.dhan.domain import Exchange, InstrumentType
from brokers.dhan.loader import InstrumentLoader
from brokers.dhan.resolver import SymbolResolver

pytestmark = [pytest.mark.dhan, pytest.mark.off_market_safe, pytest.mark.regression]


@pytest.fixture(scope="module")
def real_resolver():
    """Download/load live scrip master and populate the resolver."""
    rows = InstrumentLoader.load_cached()
    assert len(rows) > 0, "No rows loaded from Dhan scrip master"
    resolver = SymbolResolver()
    resolver.load_from_rows(rows)
    return resolver


def test_live_bidirectional_mapping(real_resolver):
    """Verify bidirectional mapping (symbol <-> security_id) for random samples."""
    all_insts = real_resolver.all_instruments()
    assert len(all_insts) > 1000, "Too few instruments loaded"

    # Group by exchange to ensure all segments are covered
    by_exchange: dict[Exchange, list] = {}
    for inst in all_insts:
        by_exchange.setdefault(inst.exchange, []).append(inst)

    # We want to check at least these exchanges
    expected_exchanges = [Exchange.NSE, Exchange.BSE, Exchange.NFO, Exchange.MCX, Exchange.CDS]
    for exch in expected_exchanges:
        assert exch in by_exchange, f"Exchange {exch} missing from loaded instruments"
        insts = by_exchange[exch]

        # Take a random sample of up to 50 instruments
        sample_size = min(len(insts), 50)
        sample = random.sample(insts, sample_size)

        for inst in sample:
            # 1. Reverse lookup: security_id -> Instrument
            rev = real_resolver.get_by_security_id(inst.security_id)
            assert rev is not None, f"Failed reverse lookup for security_id {inst.security_id}"
            assert rev.security_id == inst.security_id
            assert rev.symbol == inst.symbol
            assert rev.exchange == inst.exchange

            # 2. Forward lookup: symbol -> Instrument
            fwd = real_resolver.get_by_symbol(inst.symbol, inst.exchange.value)
            assert fwd is not None, (
                f"Failed forward lookup for symbol {inst.symbol} on {inst.exchange}"
            )
            assert fwd.symbol == inst.symbol
            assert fwd.exchange == inst.exchange

            # 3. Direct resolve method
            resolved = real_resolver.resolve(inst.symbol, inst.exchange.value)
            assert resolved.symbol == inst.symbol
            assert resolved.exchange == inst.exchange

            # 4. If underlying or sm_symbol_name is present, verify alternate keys
            if inst.sm_symbol_name:
                alt = real_resolver.get_by_symbol(inst.sm_symbol_name, inst.exchange.value)
                # For index options/futures or commodities, the sm_symbol_name should resolve to a valid contract
                # (usually the first loaded one matching that alternate key)
                if alt is not None:
                    assert alt.exchange == inst.exchange
                    if inst.instrument_type in (InstrumentType.OPTION, InstrumentType.FUTURE):
                        assert (
                            alt.underlying == inst.underlying
                            or alt.sm_symbol_name == inst.sm_symbol_name
                        )

            # 5. Check if canonical symbol resolves
            if inst.canonical_symbol:
                canon = real_resolver.get_by_symbol(inst.canonical_symbol, inst.exchange.value)
                assert canon is not None, f"Failed canonical lookup for {inst.canonical_symbol}"
                assert canon.exchange == inst.exchange
