from __future__ import annotations

from brokers.upstox.instruments.segment_mapper import UpstoxSegmentMapper
from domain import ExchangeSegment


def test_known_upstox_segments_map():
    assert UpstoxSegmentMapper.to_safe("NSE_EQ") is ExchangeSegment.NSE
    assert UpstoxSegmentMapper.to_safe("BSE_EQ") is ExchangeSegment.BSE
    assert UpstoxSegmentMapper.to_safe("NSE_FO") is ExchangeSegment.NSE_FNO
    assert UpstoxSegmentMapper.to_safe("BSE_FO") is ExchangeSegment.BSE_FNO
    assert UpstoxSegmentMapper.to_safe("MCX_FO") is ExchangeSegment.MCX
    assert UpstoxSegmentMapper.to_safe("NSE_COM") is ExchangeSegment.MCX
    assert UpstoxSegmentMapper.to_safe("NSE_INDEX") is ExchangeSegment.IDX_I
    assert UpstoxSegmentMapper.to_safe("BSE_INDEX") is ExchangeSegment.IDX_I
    assert UpstoxSegmentMapper.to_safe("MCX_INDEX") is ExchangeSegment.IDX_I
    assert UpstoxSegmentMapper.to_safe("GLOBAL_INDEX") is ExchangeSegment.IDX_I
    assert UpstoxSegmentMapper.to_safe("NCD_FO") is ExchangeSegment.NSE_CURRENCY
    assert UpstoxSegmentMapper.to_safe("BCD_FO") is ExchangeSegment.BSE_CURRENCY


def test_unknown_segment_defaults_to_nse():
    assert UpstoxSegmentMapper.to_safe("UNKNOWN") is ExchangeSegment.NSE
    assert UpstoxSegmentMapper.to_safe("") is ExchangeSegment.NSE
    assert UpstoxSegmentMapper.to_safe("ZOMBO") is ExchangeSegment.NSE


def test_segment_to_wire():
    assert UpstoxSegmentMapper.to_wire(ExchangeSegment.NSE) == "NSE_EQ"
    assert UpstoxSegmentMapper.to_wire(ExchangeSegment.BSE) == "BSE_EQ"
    assert UpstoxSegmentMapper.to_wire(ExchangeSegment.NSE_FNO) == "NSE_FO"
    assert UpstoxSegmentMapper.to_wire(ExchangeSegment.MCX) == "MCX_FO"
    assert UpstoxSegmentMapper.to_wire(ExchangeSegment.IDX_I) == "NSE_INDEX"


def test_segment_to_wire_string_input():
    assert UpstoxSegmentMapper.to_wire("NSE_EQ") == "NSE_EQ"
    assert UpstoxSegmentMapper.to_wire("") == "NSE_EQ"
    assert UpstoxSegmentMapper.to_wire(None) == "NSE_EQ"
