"""Tests for domain.status_mapper — StatusMapperRegistry and common mappings."""

from __future__ import annotations

import pytest

from domain.status_mapper import (
    COMMON_STATUS_MAP,
    StatusMapperRegistry,
    UnmappedBrokerStatusError,
)
from domain.types import OrderStatus


class TestStatusMapperRegistryNormalize:
    def test_canonical_filled(self):
        assert StatusMapperRegistry.normalize("FILLED") == OrderStatus.FILLED

    def test_canonical_open(self):
        assert StatusMapperRegistry.normalize("OPEN") == OrderStatus.OPEN

    def test_complete_maps_to_filled(self):
        assert StatusMapperRegistry.normalize("COMPLETE") == OrderStatus.FILLED

    def test_executed_maps_to_filled(self):
        assert StatusMapperRegistry.normalize("EXECUTED") == OrderStatus.FILLED

    def test_partial_maps_to_partially_filled(self):
        assert StatusMapperRegistry.normalize("PARTIAL") == OrderStatus.PARTIALLY_FILLED

    def test_transit_maps_to_open(self):
        assert StatusMapperRegistry.normalize("TRANSIT") == OrderStatus.OPEN

    def test_empty_string_returns_unknown(self):
        assert StatusMapperRegistry.normalize("") == OrderStatus.UNKNOWN

    def test_whitespace_stripped(self):
        assert StatusMapperRegistry.normalize("  FILLED  ") == OrderStatus.FILLED

    def test_case_insensitive(self):
        assert StatusMapperRegistry.normalize("filled") == OrderStatus.FILLED

    def test_space_replaced_with_underscore(self):
        assert StatusMapperRegistry.normalize("PARTIALLY FILLED") == OrderStatus.PARTIALLY_FILLED

    def test_garbage_returns_unknown(self):
        assert StatusMapperRegistry.normalize("TOTALLY_MADE_UP") == OrderStatus.UNKNOWN


class TestStatusMapperRegistryNormalizeStrict:
    def test_known_status_returns_value(self):
        assert StatusMapperRegistry.normalize_strict("FILLED") == OrderStatus.FILLED

    def test_unknown_raises(self):
        with pytest.raises(UnmappedBrokerStatusError, match="TOTALLY_MADE_UP"):
            StatusMapperRegistry.normalize_strict("TOTALLY_MADE_UP")

    def test_empty_raises(self):
        with pytest.raises(UnmappedBrokerStatusError):
            StatusMapperRegistry.normalize_strict("")


class TestUnmappedBrokerStatusError:
    def test_stores_broker_status(self):
        err = UnmappedBrokerStatusError("WEIRD_STATUS")
        assert err.broker_status == "WEIRD_STATUS"
        assert "WEIRD_STATUS" in str(err)

    def test_is_value_error(self):
        assert issubclass(UnmappedBrokerStatusError, ValueError)


class TestStatusMapperRegistryRegister:
    def test_register_custom_mapping(self):
        StatusMapperRegistry.register("test_broker", {"CUSTOM_OK": OrderStatus.FILLED})
        assert StatusMapperRegistry.normalize("CUSTOM_OK") == OrderStatus.FILLED
        # Clean up
        del StatusMapperRegistry._mappings["test_broker"]
        StatusMapperRegistry._merged = None

    def test_common_map_registered_at_load(self):
        for key in COMMON_STATUS_MAP:
            assert StatusMapperRegistry.normalize(key) == COMMON_STATUS_MAP[key]
