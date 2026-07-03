"""Honest Dhan capabilities model tests."""

from __future__ import annotations

from brokers.adapters.dhan.capabilities import dhan_capabilities


def test_dhan_capabilities_is_broker_capabilities():
    caps = dhan_capabilities()
    assert caps.broker_id == "dhan"
    assert caps.supports_place_order
    assert caps.supports_native_slice_order
    assert caps.supports_super_order
    assert not caps.supports("gtt")  # no false GTT flag
    assert caps.stream_limits is not None
    assert caps.supports_depth_20_ws
