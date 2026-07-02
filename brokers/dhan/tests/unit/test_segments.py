"""Unit tests for segment constant mappings."""

from brokers.dhan.domain import Exchange
from brokers.dhan.segments import (
    _COMPACT_SEGMENT_MAP,
    EXCHANGE_TO_SEGMENT,
    NUMERIC_TO_SEGMENT,
    SEGMENT_TO_EXCHANGE,
    from_sdk_int,
    to_dhan_wire,
    to_sdk_int,
)


def test_exchange_to_segment_completeness():
    all_exchanges = {e.value for e in Exchange}
    mapped = set(EXCHANGE_TO_SEGMENT.keys())
    assert all_exchanges == mapped, f"Missing mappings for: {all_exchanges - mapped}"


def test_reverse_mapping_consistency():
    for exch, segment in EXCHANGE_TO_SEGMENT.items():
        assert SEGMENT_TO_EXCHANGE[segment] == exch, (
            f"Reverse mismatch: {segment} -> {SEGMENT_TO_EXCHANGE[segment]} != {exch}"
        )
    assert SEGMENT_TO_EXCHANGE["BSE_CURRENCY"] == "BCD"


def test_compact_segment_map_has_mcx():
    assert _COMPACT_SEGMENT_MAP[("MCX", "M")] == "MCX_COMM"


def test_numeric_segment_codes():
    assert NUMERIC_TO_SEGMENT[0] == "IDX_I"
    assert NUMERIC_TO_SEGMENT[1] == "NSE_EQ"
    assert NUMERIC_TO_SEGMENT[2] == "NSE_FNO"
    assert NUMERIC_TO_SEGMENT[3] == "NSE_CURRENCY"
    assert NUMERIC_TO_SEGMENT[4] == "BSE_EQ"
    assert NUMERIC_TO_SEGMENT[5] == "MCX_COMM"


def test_to_dhan_wire_mcx():
    from domain.types import ExchangeSegment

    assert to_dhan_wire(ExchangeSegment.MCX) == "MCX_COMM"
    assert to_dhan_wire("MCX") == "MCX_COMM"


def test_sdk_int_roundtrip():
    from domain.types import ExchangeSegment

    assert from_sdk_int(5) is ExchangeSegment.MCX
    assert to_sdk_int(ExchangeSegment.MCX) == 5
