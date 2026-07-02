"""REF-31: pickle-loader security tests.

The previous :meth:`InstrumentLoader._migrate_pickle_to_json` used
``pickle.load`` on a file in the cache directory. That was a CWE-502
arbitrary-code-execution vulnerability: an attacker who can write to
the cache directory (compromised CI, malicious dependency, shared
container) could achieve code execution in the trading process.

The contract this module enforces is:

1. The loader MUST NOT call :func:`pickle.load` on any file in the
   cache directory.
2. A legacy ``.pkl`` file MUST be quarantined (renamed to
   ``.pkl.quarantine``) so the loader can no longer pick it up.
3. If the quarantine rename fails, the loader MUST continue to
   operate by rebuilding from the authoritative JSON source.

These tests construct a real ``.pkl`` file in a temporary directory
and verify the loader never invokes ``pickle.load`` on it.
"""

from __future__ import annotations

import json
import pickle
import sys
import types
from pathlib import Path

from brokers.upstox.instruments.loader import UpstoxInstrumentLoader


def _write_minimal_upstox_json(path: Path) -> None:
    """Write a minimal valid Upstox instruments JSON source."""
    payload = [
        {
            "instrument_key": "NSE_EQ|RELIANCE",
            "exchange": "NSE",
            "segment": "NSE_EQ",
            "instrument_type": "EQ",
            "symbol": "RELIANCE",
            "trading_symbol": "RELIANCE",
            "name": "Reliance Industries",
            "isin": "INE002A01018",
            "lot_size": 1,
            "tick_size": 0.05,
            "expiry": None,
            "strike": None,
            "freeze_qty": None,
            "minimum_lot": None,
            "short_name": "RELIANCE",
            "company_name": "Reliance Industries Limited",
        }
    ]
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_pickle_cache_is_quarantined_not_loaded(tmp_path: Path) -> None:
    """A legacy .pkl must be quarantined, never unpickled."""
    src = tmp_path / "instruments.json"
    _write_minimal_upstox_json(src)
    pkl = src.with_suffix(".pkl")
    # Write a benign pickle so a buggy implementation would actually
    # call pickle.load and get a "valid" result, masking the bug.
    pkl.write_bytes(pickle.dumps(["this would have been loaded unsafely"]))

    loader = UpstoxInstrumentLoader()
    defs = loader.load(src)

    # Quarantine file MUST exist, pickle MUST NOT.
    assert pkl.with_suffix(pkl.suffix + ".quarantine").exists()
    assert not pkl.exists(), f"Unsafe pickle file still present: {pkl}"

    # The loader still produced instruments from the JSON source.
    assert len(defs) == 1
    assert defs[0].symbol == "RELIANCE"


def test_pickle_load_is_not_invoked(monkeypatch, tmp_path: Path) -> None:
    """A monkeypatched pickle.load MUST NOT be called by the loader."""
    src = tmp_path / "instruments.json"
    _write_minimal_upstox_json(src)
    pkl = src.with_suffix(".pkl")
    pkl.write_bytes(pickle.dumps(["would-be-unsafe"]))

    # Inject a sentinel pickle module that raises if anyone calls .load.
    sentinel = types.ModuleType("pickle")

    def _explode(*_args, **_kwargs):
        raise AssertionError("pickle.load was called by the loader")

    sentinel.load = _explode
    sentinel.loads = _explode
    monkeypatch.setitem(sys.modules, "pickle", sentinel)

    loader = UpstoxInstrumentLoader()
    loader.load(src)
    # If we reach this line, no pickle.load was called.


def test_pickle_quarantine_when_destination_exists(tmp_path: Path) -> None:
    """If a .pkl.quarantine already exists, the loader must not crash."""
    src = tmp_path / "instruments.json"
    _write_minimal_upstox_json(src)
    pkl = src.with_suffix(".pkl")
    pkl.write_bytes(pickle.dumps([]))
    quarantine = pkl.with_suffix(pkl.suffix + ".quarantine")
    quarantine.write_bytes(b"existing quarantine from a prior run")

    loader = UpstoxInstrumentLoader()
    defs = loader.load(src)
    # Either the quarantine was overwritten (rename is atomic) or the
    # loader fell through to the JSON path. Both are acceptable; what
    # matters is no exception and no pickle.load.
    assert len(defs) == 1
