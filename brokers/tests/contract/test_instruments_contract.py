"""Contract tests — verify any instruments adapter satisfies the InstrumentPort protocol."""

from __future__ import annotations

import pytest
from brokers.domain import InstrumentInfo
from brokers.ports import InstrumentPort


class _FakeInstruments:
    def search(self, query: str, limit: int = 10) -> list[InstrumentInfo]:
        return [InstrumentInfo(symbol="RELIANCE", exchange="NSE")]

    def resolve(self, symbol: str, exchange: str = "NSE") -> InstrumentInfo | None:
        return InstrumentInfo(symbol=symbol, exchange=exchange)

    def load(self) -> None:
        pass


@pytest.mark.contract
class TestInstrumentContract:
    def test_satisfies_protocol(self):
        adapter = _FakeInstruments()
        assert isinstance(adapter, InstrumentPort)

    def test_search_returns_list(self):
        adapter = _FakeInstruments()
        result = adapter.search("REL")
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], InstrumentInfo)

    def test_resolve_returns_instrument_or_none(self):
        adapter = _FakeInstruments()
        result = adapter.resolve("RELIANCE")
        assert result is None or isinstance(result, InstrumentInfo)
        if result is not None:
            assert result.symbol == "RELIANCE"

    def test_load_returns_none(self):
        adapter = _FakeInstruments()
        result = adapter.load()
        assert result is None
