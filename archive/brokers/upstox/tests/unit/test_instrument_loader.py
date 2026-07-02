from __future__ import annotations

import json
from pathlib import Path

import pytest

from brokers.upstox.instruments.loader import UpstoxInstrumentLoader
from brokers.upstox.instruments.resolver import UpstoxInstrumentResolver


def _write_fixture(tmp_path: Path) -> Path:
    data = [
        {
            "instrument_key": "NSE_EQ|INE001A01023",
            "exchange": "NSE",
            "segment": "NSE_EQ",
            "instrument_type": "EQ",
            "symbol": "RELIANCE",
            "trading_symbol": "RELIANCE",
            "name": "RELIANCE INDUSTRIES LTD",
            "isin": "INE001A01023",
            "lot_size": 1,
            "tick_size": 5.0,
            "freeze_qty": 2700,
        },
        {
            "instrument_key": "NSE_FO|12345",
            "exchange": "NSE",
            "segment": "NSE_FO",
            "instrument_type": "FUT",
            "symbol": "RELIANCE26JUNFUT",
            "trading_symbol": "RELIANCE26JUNFUT",
            "name": "RELIANCE FUT 26 JUN",
            "lot_size": 250,
            "tick_size": 0.05,
            "expiry": "2026-06-26",
            "underlying_symbol": "RELIANCE",
            "freeze_qty": 1800,
        },
        {
            "instrument_key": "NSE_INDEX|Nifty 50",
            "exchange": "NSE",
            "segment": "NSE_INDEX",
            "instrument_type": "INDEX",
            "symbol": "Nifty 50",
            "trading_symbol": "NIFTY",
            "name": "NIFTY 50",
            "lot_size": 1,
            "tick_size": 0.05,
        },
        {
            "instrument_key": "MALFORMED",
            "segment": "BAD_SEGMENT",
        },
    ]
    p = tmp_path / "instruments.json"
    p.write_text(json.dumps(data))
    return p


def test_load_returns_list_of_definitions(tmp_path):
    loader = UpstoxInstrumentLoader()
    defs = loader.load(_write_fixture(tmp_path))
    assert len(defs) == 3
    assert defs[0].symbol == "RELIANCE"
    assert defs[0].is_equity
    assert defs[0].freeze_qty == 2700
    assert defs[1].is_future
    assert defs[1].expiry == "2026-06-26"
    assert defs[2].is_index
    assert defs[2].instrument_key == "NSE_INDEX|Nifty 50"


def test_load_skips_malformed_records(tmp_path):
    loader = UpstoxInstrumentLoader()
    defs = loader.load(_write_fixture(tmp_path))
    assert all(d.instrument_key != "MALFORMED" for d in defs)


def test_load_gz_file(tmp_path):
    import gzip

    p = tmp_path / "instruments.json.gz"
    with gzip.open(p, "wt", encoding="utf-8") as fp:
        json.dump([{"instrument_key": "NSE_EQ|X", "segment": "NSE_EQ", "symbol": "X"}], fp)
    loader = UpstoxInstrumentLoader()
    defs = loader.load(p)
    assert len(defs) == 1


def test_resolver_register_and_resolve():
    resolver = UpstoxInstrumentResolver()
    from brokers.upstox.instruments.definition import UpstoxInstrumentDefinition

    d = UpstoxInstrumentDefinition(
        instrument_key="NSE_EQ|INE001A01023",
        exchange_segment="NSE_EQ",
        symbol="RELIANCE",
        trading_symbol="RELIANCE",
        name="RELIANCE",
        instrument_type="EQ",
    )
    resolver.register(d)
    assert resolver.is_loaded() is True
    assert resolver.resolve(instrument_key="NSE_EQ|INE001A01023") is d
    assert resolver.resolve(symbol="RELIANCE", exchange_segment="NSE_EQ") is d
    assert resolver.resolve(instrument_key="NOPE") is None


def test_resolver_require_raises_when_missing():
    resolver = UpstoxInstrumentResolver()
    with pytest.raises(ValueError):
        resolver.require(instrument_key="NOPE")


def test_resolver_search_prefix():
    resolver = UpstoxInstrumentResolver()
    from brokers.upstox.instruments.definition import UpstoxInstrumentDefinition

    for sym in ["RELIANCE", "RELAXO", "TCS", "INFY"]:
        resolver.register(
            UpstoxInstrumentDefinition(
                instrument_key=f"NSE_EQ|{sym}",
                exchange_segment="NSE_EQ",
                symbol=sym,
                trading_symbol=sym,
                name=sym,
                instrument_type="EQ",
            )
        )
    results = resolver.search("REL")
    assert {d.symbol for d in results} == {"RELIANCE", "RELAXO"}


def test_resolver_search_filters_by_segment():
    resolver = UpstoxInstrumentResolver()
    from brokers.upstox.instruments.definition import UpstoxInstrumentDefinition

    resolver.register(
        UpstoxInstrumentDefinition(
            instrument_key="NSE_EQ|RELIANCE",
            exchange_segment="NSE_EQ",
            symbol="RELIANCE",
            trading_symbol="RELIANCE",
            name="RELIANCE",
            instrument_type="EQ",
        )
    )
    resolver.register(
        UpstoxInstrumentDefinition(
            instrument_key="BSE_EQ|RELIANCE",
            exchange_segment="BSE_EQ",
            symbol="RELIANCE",
            trading_symbol="RELIANCE",
            name="RELIANCE-BSE",
            instrument_type="EQ",
        )
    )
    only_nse = resolver.search("REL", exchange_segment="NSE_EQ")
    assert len(only_nse) == 1
    assert only_nse[0].exchange_segment == "NSE_EQ"


def test_resolver_reset():
    resolver = UpstoxInstrumentResolver()
    from brokers.upstox.instruments.definition import UpstoxInstrumentDefinition

    resolver.register(
        UpstoxInstrumentDefinition(instrument_key="K", symbol="X", exchange_segment="NSE_EQ")
    )
    assert len(resolver) == 1
    resolver.reset()
    assert len(resolver) == 0
    assert resolver.is_loaded() is False
