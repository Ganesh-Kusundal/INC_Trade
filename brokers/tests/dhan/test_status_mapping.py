"""Tests for Dhan shared status mapping module."""

from __future__ import annotations

import pytest

from brokers.dhan.status_mapping import (
    DHAN_STATUS_TO_ENUM,
    DHAN_STATUS_TO_STRING,
    normalize_status,
    to_order_status,
)
from brokers.domain.enums import OrderStatus


class TestNormalizeStatus:
    def test_all_wire_statuses_mapped(self):
        known = [
            "TRANSIT", "PENDING", "PENDING_ORDER", "VALIDATED", "AMO_RECEIVED",
            "OPEN", "TRADED", "FILLED", "PART_TRADED", "PART_FILLED",
            "EXPIRED", "REJECTED", "CANCELLED", "CANCELED", "MODIFIED",
        ]
        for status in known:
            result = normalize_status(status)
            assert result != "UNKNOWN", f"{status} mapped to UNKNOWN"

    def test_case_insensitive(self):
        assert normalize_status("traded") == "FILLED"
        assert normalize_status("Traded") == "FILLED"

    def test_unknown_returns_unknown(self):
        assert normalize_status("BOGUS") == "UNKNOWN"

    def test_empty_returns_unknown(self):
        assert normalize_status("") == "UNKNOWN"


class TestToOrderStatus:
    def test_all_statuses_map_to_valid_enum(self):
        for key, enum_val in DHAN_STATUS_TO_ENUM.items():
            assert isinstance(enum_val, OrderStatus), f"{key} maps to non-enum"

    def test_filled_maps_correctly(self):
        assert to_order_status("FILLED") == OrderStatus.FILLED
        assert to_order_status("TRADED") == OrderStatus.FILLED

    def test_cancelled_both_spellings(self):
        assert to_order_status("CANCELLED") == OrderStatus.CANCELLED
        assert to_order_status("CANCELED") == OrderStatus.CANCELLED

    def test_unknown_returns_unknown_enum(self):
        assert to_order_status("NONEXISTENT") == OrderStatus.UNKNOWN


class TestConsistency:
    def test_string_and_enum_mappings_agree(self):
        string_statuses = set(DHAN_STATUS_TO_STRING.keys())
        enum_statuses = set(DHAN_STATUS_TO_ENUM.keys())
        assert string_statuses == enum_statuses, (
            f"Mismatch: only in string={string_statuses - enum_statuses}, "
            f"only in enum={enum_statuses - string_statuses}"
        )
