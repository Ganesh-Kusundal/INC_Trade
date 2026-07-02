"""Tests for DhanConnection — adapter wiring and instrument loading."""

from __future__ import annotations

import os
import sys

# Ensure project root is on sys.path for direct pytest invocation
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

from brokers.dhan.connection import DhanConnection
from brokers.dhan.resolver import SymbolResolver
from brokers.dhan.tests.conftest import SAMPLE_ROWS, FakeHttpClient


class TestDhanConnection:
    """Verify that DhanConnection wires every adapter correctly."""

    def _make_connection(self) -> tuple[DhanConnection, FakeHttpClient, SymbolResolver]:
        client = FakeHttpClient()
        resolver = SymbolResolver()
        conn = DhanConnection(client=client, resolver=resolver)
        return conn, client, resolver

    # -- adapter wiring --------------------------------------------------

    def test_all_adapters_wired(self):
        """Every adapter property must return a non-None object."""
        conn, _, _ = self._make_connection()

        assert conn.market_data is not None
        assert conn.orders is not None
        assert conn.portfolio is not None
        assert conn.options is not None
        assert conn.futures is not None
        assert conn.historical is not None
        assert conn.margin is not None
        assert conn.alerts is not None

    # -- instruments property --------------------------------------------

    def test_instruments_property(self):
        """connection.instruments must be the exact resolver passed in."""
        conn, _, resolver = self._make_connection()

        assert conn.instruments is resolver

    # -- load_instruments from rows --------------------------------------

    def test_load_instruments_from_rows(self):
        """Loading rows into the resolver updates its stats."""
        _conn, _, resolver = self._make_connection()

        # Before loading: resolver should report 0 instruments
        stats_before = resolver.stats()
        assert stats_before["loaded"] is False
        assert stats_before["total"] == 0

        # Load sample rows directly into the resolver
        resolver.load_from_rows(SAMPLE_ROWS)

        stats_after = resolver.stats()
        assert stats_after["loaded"] is True
        assert stats_after["total"] > 0

        # Verify specific instruments are resolvable
        reliance = resolver.resolve("RELIANCE", "NSE")
        assert reliance.security_id == "2885"

        nifty = resolver.resolve("NIFTY", "INDEX")
        assert nifty.security_id == "13"
