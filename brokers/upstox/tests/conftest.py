"""Shared test fixtures for brokers.upstox tests.

Mirrors the proven pattern from brokers.dhan.tests.conftest.py (318 lines)
adapted for Upstox-specific API response formats and instrument structures.
"""

from __future__ import annotations

from typing import Any

import pytest

from brokers.upstox.instruments.resolver import UpstoxInstrumentResolver

# ---------------------------------------------------------------------------
# Fake HTTP client — sync mock replacing Upstox HTTP client
# ---------------------------------------------------------------------------


class FakeHttpClient:
    """Drop-in replacement for Upstox HTTP client in unit tests.

    Records every request and returns pre-configured responses.
    Supports Upstox-specific response formats (status/data wrapper).
    """

    def __init__(self, api_key: str = "TEST_API_KEY", access_token: str = "TEST_TOKEN"):
        self.api_key = api_key
        self.access_token = access_token
        self._responses: dict[tuple[str, str], Any] = {}
        self._side_effects: dict[tuple[str, str], Exception] = {}
        self.calls: list[tuple[str, str, Any]] = []

    def set_response(self, method: str, path: str, response: Any) -> None:
        """Configure a mock response for a specific endpoint."""
        self._responses[(method, path)] = response

    def set_side_effect(self, method: str, path: str, exc: Exception) -> None:
        """Configure an exception to be raised for a specific endpoint."""
        self._side_effects[(method, path)] = exc

    def post(self, path: str, json: Any = None, headers: dict[str, str] | None = None) -> Any:
        """Simulate POST request."""
        self.calls.append(("POST", path, json))
        key = ("POST", path)
        if key in self._side_effects:
            raise self._side_effects[key]
        return self._responses.get(key, {"status": "success", "data": {}})

    def get(self, path: str, headers: dict[str, str] | None = None) -> Any:
        """Simulate GET request."""
        self.calls.append(("GET", path, None))
        key = ("GET", path)
        if key in self._side_effects:
            raise self._side_effects[key]
        return self._responses.get(key, {"status": "success", "data": {}})

    def put(self, path: str, json: Any = None, headers: dict[str, str] | None = None) -> Any:
        """Simulate PUT request."""
        self.calls.append(("PUT", path, json))
        key = ("PUT", path)
        if key in self._side_effects:
            raise self._side_effects[key]
        return self._responses.get(key, {"status": "success", "data": {}})

    def delete(self, path: str, headers: dict[str, str] | None = None) -> Any:
        """Simulate DELETE request."""
        self.calls.append(("DELETE", path, None))
        key = ("DELETE", path)
        if key in self._side_effects:
            raise self._side_effects[key]
        return self._responses.get(key, {"status": "success", "data": {}})

    def update_token(self, token: str) -> None:
        """Update the access token."""
        self.access_token = token

    def close(self) -> None:
        """Close the HTTP session (no-op in tests)."""
        pass

    @property
    def call_count(self) -> int:
        """Return total number of recorded calls."""
        return len(self.calls)

    def calls_for(self, method: str, path: str) -> list[Any]:
        """Return all recorded calls for a specific method and path."""
        return [j for m, p, j in self.calls if m == method and p == path]


# ---------------------------------------------------------------------------
# Sample instrument definitions (Upstox format)
# ---------------------------------------------------------------------------

SAMPLE_INSTRUMENTS = [
    # ── Index ──
    {
        "instrument_key": "NSE_INDEX|Nifty 50",
        "exchange_segment": "NSE_INDEX",
        "symbol": "NIFTY",
        "name": "Nifty 50",
        "instrument_type": "INDEX",
        "tick_size": 0.05,
        "lot_size": 1,
    },
    # ── NSE Equity ──
    {
        "instrument_key": "NSE_EQ|RELIANCE",
        "exchange_segment": "NSE_EQ",
        "symbol": "RELIANCE",
        "name": "Reliance Industries Ltd",
        "instrument_type": "EQUITY",
        "tick_size": 0.05,
        "lot_size": 1,
    },
    {
        "instrument_key": "NSE_EQ|INFY",
        "exchange_segment": "NSE_EQ",
        "symbol": "INFY",
        "name": "Infosys Ltd",
        "instrument_type": "EQUITY",
        "tick_size": 0.05,
        "lot_size": 1,
    },
    # ── NSE F&O Option (CE) ──
    {
        "instrument_key": "NFO_OPT|NIFTY26JUN26C25000",
        "exchange_segment": "NFO_OPT",
        "symbol": "NIFTY26JUN26C25000",
        "name": "NIFTY 26 JUN 2026 CE 25000",
        "instrument_type": "OPTION",
        "tick_size": 0.05,
        "lot_size": 75,
        "expiry_date": "2026-06-26",
        "strike_price": 25000.0,
        "option_type": "CE",
    },
    # ── NSE F&O Option (PE) ──
    {
        "instrument_key": "NFO_OPT|NIFTY26JUN26P25000",
        "exchange_segment": "NFO_OPT",
        "symbol": "NIFTY26JUN26P25000",
        "name": "NIFTY 26 JUN 2026 PE 25000",
        "instrument_type": "OPTION",
        "tick_size": 0.05,
        "lot_size": 75,
        "expiry_date": "2026-06-26",
        "strike_price": 25000.0,
        "option_type": "PE",
    },
    # ── NSE F&O Future ──
    {
        "instrument_key": "NFO_FUT|NIFTY26JUN26FUT",
        "exchange_segment": "NFO_FUT",
        "symbol": "NIFTY26JUN26FUT",
        "name": "NIFTY 26 JUN 2026 FUT",
        "instrument_type": "FUTURE",
        "tick_size": 0.05,
        "lot_size": 75,
        "expiry_date": "2026-06-26",
    },
    # ── BSE Equity ──
    {
        "instrument_key": "BSE_EQ|532240",
        "exchange_segment": "BSE_EQ",
        "symbol": "532240",
        "name": "Reliance Industries Ltd",
        "instrument_type": "EQUITY",
        "tick_size": 0.05,
        "lot_size": 1,
    },
    # ── MCX Commodity Future ──
    {
        "instrument_key": "MCX_FUT|CRUDEOIL18JUN26FUT",
        "exchange_segment": "MCX_FUT",
        "symbol": "CRUDEOIL18JUN26FUT",
        "name": "CRUDEOIL 18 JUN 2026 FUT",
        "instrument_type": "FUTURE",
        "tick_size": 1.0,
        "lot_size": 100,
        "expiry_date": "2026-06-18",
    },
]


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_client():
    """Provide a FakeHttpClient instance for mocking Upstox API calls."""
    return FakeHttpClient()


@pytest.fixture
def sample_instruments():
    """Provide sample Upstox instrument definitions."""
    return list(SAMPLE_INSTRUMENTS)


@pytest.fixture
def resolver(sample_instruments):
    """Provide a UpstoxInstrumentResolver loaded with sample instruments."""
    r = UpstoxInstrumentResolver()
    r.load_from_instruments(sample_instruments)
    return r
