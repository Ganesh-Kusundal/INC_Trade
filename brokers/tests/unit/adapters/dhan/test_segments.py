"""Segment resolution helper tests."""

from __future__ import annotations

from brokers.adapters.dhan.segments import resolve_exchange, resolve_segment


def test_resolve_segment_nse():
    assert resolve_segment("NSE") == "NSE_EQ"


def test_resolve_segment_nfo():
    assert resolve_segment("NFO") == "NSE_FNO"


def test_resolve_exchange_roundtrip():
    assert resolve_exchange(resolve_segment("MCX")) == "MCX"
