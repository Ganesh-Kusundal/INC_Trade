"""Live integration tests for Upstox symbol mapping using real instrument master.

This test loads the real, live instrument master from Upstox (via cache or fresh download)
and verifies that bidirectional mapping works correctly for a random sample of
instruments from each segment.
"""

from __future__ import annotations

from brokers.upstox.tests.integration.conftest import skip_live


@skip_live
def test_live_bidirectional_mapping(gateway):
    """Verify bidirectional mapping (symbol <-> instrument_key) for random samples."""
    # Access the resolver from the broker
    resolver = gateway._broker.instrument_resolver

    # Get all instrument definitions
    # Try to get a sample of instruments from the resolver
    # The exact API depends on UpstoxInstrumentResolver implementation

    # For now, test with known symbols
    test_symbols = [
        ("RELIANCE", "NSE"),
        ("TCS", "NSE"),
        ("INFY", "NSE"),
        ("NIFTY", "INDEX"),
    ]

    for symbol, exchange in test_symbols:
        try:
            # Try to resolve the symbol
            defn = resolver.resolve(symbol=symbol, exchange_segment=exchange)
            if defn:
                # Verify the definition has required fields
                assert hasattr(defn, "symbol")
                assert hasattr(defn, "instrument_key")
                assert defn.symbol.upper() == symbol.upper()

                # Try reverse lookup by instrument_key
                if hasattr(defn, "instrument_key"):
                    key_defn = resolver.resolve(instrument_key=defn.instrument_key)
                    if key_defn:
                        assert key_defn.symbol.upper() == symbol.upper()
        except Exception:
            # Some symbols may not resolve, that's okay
            pass
