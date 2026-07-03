"""Unit tests for UpstoxInstrumentLoader."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from brokers.adapters.upstox.instrument_loader import UpstoxInstrumentLoader


class TestUpstoxInstrumentLoader:
    def test_cache_validity(self, tmp_path: Path):
        loader = UpstoxInstrumentLoader()
        cache = tmp_path / "complete.json.gz"
        cache.write_bytes(b"x")
        assert loader._is_cache_valid(cache) is True

    def test_iter_definitions_from_gz(self, tmp_path: Path):
        record = {
            "instrument_key": "NSE_EQ|RELIANCE",
            "symbol": "RELIANCE",
            "segment": "NSE_EQ",
            "exchange": "NSE",
            "lot_size": 1,
        }
        gz_path = tmp_path / "test.json.gz"
        with gzip.open(gz_path, "wt", encoding="utf-8") as f:
            json.dump([record], f)
        loader = UpstoxInstrumentLoader()
        defs = list(loader.iter_definitions(gz_path))
        assert len(defs) == 1
        assert defs[0].symbol == "RELIANCE"
