"""Shared test fixtures for brokers.dhan tests."""

from __future__ import annotations

import os
from typing import Any

import pytest

from brokers.dhan.resolver import SymbolResolver


@pytest.fixture(autouse=True)
def _clean_dhan_token_state_dir():
    """Save and restore DHAN_TOKEN_STATE_DIR to prevent cross-test contamination."""
    saved = os.environ.get("DHAN_TOKEN_STATE_DIR")
    yield
    if saved is None:
        os.environ.pop("DHAN_TOKEN_STATE_DIR", None)
    else:
        os.environ["DHAN_TOKEN_STATE_DIR"] = saved


@pytest.fixture(autouse=True)
def _reset_account_connection_registry():
    """Prevent AccountConnectionRegistry from leaking gateways across tests."""
    from brokers.dhan.account_registry import AccountConnectionRegistry

    AccountConnectionRegistry.release_all()
    yield
    AccountConnectionRegistry.release_all()

# ---------------------------------------------------------------------------
# Fake HTTP client — sync mock replacing DhanHttpClient
# ---------------------------------------------------------------------------


class FakeHttpClient:
    """Drop-in replacement for DhanHttpClient in unit tests.

    Records every request and returns pre-configured responses.
    """

    def __init__(self, client_id: str = "TEST_CLIENT", access_token: str = "TEST_TOKEN"):
        self.client_id = client_id
        self.access_token = access_token
        self._responses: dict[tuple[str, str], Any] = {}
        self._side_effects: dict[tuple[str, str], Exception] = {}
        self.calls: list[tuple[str, str, Any]] = []

    def set_response(self, method: str, path: str, response: Any) -> None:
        self._responses[(method, path)] = response

    def set_side_effect(self, method: str, path: str, exc: Exception) -> None:
        self._side_effects[(method, path)] = exc

    def post(self, path: str, json: Any = None) -> Any:
        self.calls.append(("POST", path, json))
        key = ("POST", path)
        if key in self._side_effects:
            raise self._side_effects[key]
        return self._responses.get(key, {})

    def get(self, path: str) -> Any:
        self.calls.append(("GET", path, None))
        key = ("GET", path)
        if key in self._side_effects:
            raise self._side_effects[key]
        return self._responses.get(key, {})

    def put(self, path: str, json: Any = None) -> Any:
        self.calls.append(("PUT", path, json))
        key = ("PUT", path)
        if key in self._side_effects:
            raise self._side_effects[key]
        return self._responses.get(key, {})

    def delete(self, path: str) -> Any:
        self.calls.append(("DELETE", path, None))
        key = ("DELETE", path)
        if key in self._side_effects:
            raise self._side_effects[key]
        return self._responses.get(key, {})

    def update_token(self, token: str) -> None:
        self.access_token = token

    def close(self) -> None:
        pass

    @property
    def call_count(self) -> int:
        return len(self.calls)

    def calls_for(self, method: str, path: str) -> list[Any]:
        return [j for m, p, j in self.calls if m == method and p == path]


# ---------------------------------------------------------------------------
# Sample instrument rows
# ---------------------------------------------------------------------------

SAMPLE_ROWS = [
    # ── Index ──
    {
        "SEM_TRADING_SYMBOL": "NIFTY",
        "SEM_SMST_SECURITY_ID": "13",
        "SEM_EXM_EXCH_ID": "IDX_I",
        "SEM_INSTRUMENT_NAME": "INDEX",
        "SEM_LOT_UNITS": 1,
        "SEM_TICK_SIZE": 0.05,
        "SEM_CUSTOM_SYMBOL": "Nifty 50",
        "SM_SYMBOL_NAME": "NIFTY",
    },
    # ── NSE Equity ──
    {
        "SEM_TRADING_SYMBOL": "RELIANCE",
        "SEM_SMST_SECURITY_ID": "2885",
        "SEM_EXM_EXCH_ID": "NSE_EQ",
        "SEM_INSTRUMENT_NAME": "EQUITY",
        "SEM_LOT_UNITS": 1,
        "SEM_TICK_SIZE": 0.05,
        "SEM_CUSTOM_SYMBOL": "Reliance Industries",
        "SM_SYMBOL_NAME": "RELIANCE INDUSTRIES LTD",
    },
    # ── BSE Equity ──
    {
        "SEM_TRADING_SYMBOL": "RELIANCE",
        "SEM_SMST_SECURITY_ID": "532",
        "SEM_EXM_EXCH_ID": "BSE_EQ",
        "SEM_INSTRUMENT_NAME": "EQUITY",
        "SEM_LOT_UNITS": 1,
        "SEM_TICK_SIZE": 0.05,
        "SEM_CUSTOM_SYMBOL": "Reliance Industries",
        "SM_SYMBOL_NAME": "RELIANCE INDUSTRIES LTD",
    },
    # ── NSE F&O Option (CE) ──
    {
        "SEM_TRADING_SYMBOL": "NIFTY-26Jun2026-25000-CE",
        "SEM_SMST_SECURITY_ID": "55000",
        "SEM_EXM_EXCH_ID": "NSE_FNO",
        "SEM_INSTRUMENT_NAME": "OPTIDX",
        "SEM_LOT_UNITS": 75,
        "SEM_TICK_SIZE": 0.05,
        "SEM_EXPIRY_DATE": "2026-06-26",
        "SEM_STRIKE_PRICE": 25000,
        "SEM_OPTION_TYPE": "CE",
        "SEM_CUSTOM_SYMBOL": "NIFTY 26 JUN 25000 CALL",
        "SM_SYMBOL_NAME": "NIFTY",
    },
    # ── NSE F&O Option (PE) ──
    {
        "SEM_TRADING_SYMBOL": "NIFTY-26Jun2026-25000-PE",
        "SEM_SMST_SECURITY_ID": "55001",
        "SEM_EXM_EXCH_ID": "NSE_FNO",
        "SEM_INSTRUMENT_NAME": "OPTIDX",
        "SEM_LOT_UNITS": 75,
        "SEM_TICK_SIZE": 0.05,
        "SEM_EXPIRY_DATE": "2026-06-26",
        "SEM_STRIKE_PRICE": 25000,
        "SEM_OPTION_TYPE": "PE",
        "SEM_CUSTOM_SYMBOL": "NIFTY 26 JUN 25000 PUT",
        "SM_SYMBOL_NAME": "NIFTY",
    },
    # ── NSE F&O Future ──
    {
        "SEM_TRADING_SYMBOL": "NIFTY-26Jun2026-FUT",
        "SEM_SMST_SECURITY_ID": "55100",
        "SEM_EXM_EXCH_ID": "NSE_FNO",
        "SEM_INSTRUMENT_NAME": "FUTIDX",
        "SEM_LOT_UNITS": 75,
        "SEM_TICK_SIZE": 0.05,
        "SEM_EXPIRY_DATE": "2026-06-26",
        "SEM_CUSTOM_SYMBOL": "NIFTY JUN FUT",
        "SM_SYMBOL_NAME": "NIFTY",
    },
    # ── MCX Commodity Future (near-month) ──
    {
        "SEM_TRADING_SYMBOL": "CRUDEOIL-18Jun2026-FUT",
        "SEM_SMST_SECURITY_ID": "466500",
        "SEM_EXM_EXCH_ID": "MCX_COMM",
        "SEM_INSTRUMENT_NAME": "FUTCOM",
        "SEM_LOT_UNITS": 100,
        "SEM_TICK_SIZE": 1.0,
        "SEM_EXPIRY_DATE": "2026-06-18",
        "SEM_CUSTOM_SYMBOL": "CRUDEOIL JUN FUT",
        "SM_SYMBOL_NAME": "CRUDEOIL",
    },
    # ── MCX Commodity Future (far-month) ──
    {
        "SEM_TRADING_SYMBOL": "CRUDEOIL-20Jul2026-FUT",
        "SEM_SMST_SECURITY_ID": "466501",
        "SEM_EXM_EXCH_ID": "MCX_COMM",
        "SEM_INSTRUMENT_NAME": "FUTCOM",
        "SEM_LOT_UNITS": 100,
        "SEM_TICK_SIZE": 1.0,
        "SEM_EXPIRY_DATE": "2026-07-20",
        "SEM_CUSTOM_SYMBOL": "CRUDEOIL JUL FUT",
        "SM_SYMBOL_NAME": "CRUDEOIL",
    },
    # ── MCX Commodity Option ──
    {
        "SEM_TRADING_SYMBOL": "CRUDEOIL-18Jun2026-5000-CE",
        "SEM_SMST_SECURITY_ID": "466600",
        "SEM_EXM_EXCH_ID": "MCX_COMM",
        "SEM_INSTRUMENT_NAME": "OPTFUT",
        "SEM_LOT_UNITS": 100,
        "SEM_TICK_SIZE": 1.0,
        "SEM_EXPIRY_DATE": "2026-06-18",
        "SEM_STRIKE_PRICE": 5000,
        "SEM_OPTION_TYPE": "CE",
        "SEM_CUSTOM_SYMBOL": "CRUDEOIL 18 JUN 5000 CALL",
        "SM_SYMBOL_NAME": "CRUDEOIL",
    },
    # ── GOLDM MCX Commodity Future ──
    {
        "SEM_TRADING_SYMBOL": "GOLDM-03Jul2026-FUT",
        "SEM_SMST_SECURITY_ID": "466584",
        "SEM_EXM_EXCH_ID": "MCX_COMM",
        "SEM_INSTRUMENT_NAME": "FUTCOM",
        "SEM_LOT_UNITS": 10,
        "SEM_TICK_SIZE": 1.0,
        "SEM_EXPIRY_DATE": "2026-07-03",
        "SEM_CUSTOM_SYMBOL": "GOLDM JUL FUT",
        "SM_SYMBOL_NAME": "GOLDM",
    },
    # ── GOLD MCX Commodity Future (near-month) ──
    {
        "SEM_TRADING_SYMBOL": "GOLD AUG FUT",
        "SEM_SMST_SECURITY_ID": "466583",
        "SEM_EXM_EXCH_ID": "MCX_COMM",
        "SEM_INSTRUMENT_NAME": "FUTCOM",
        "SEM_LOT_UNITS": 1,
        "SEM_TICK_SIZE": 1.0,
        "SEM_EXPIRY_DATE": "2026-08-05",
        "SEM_CUSTOM_SYMBOL": "GOLD",
        "SM_SYMBOL_NAME": "GOLD",
    },
    # ── GOLD MCX Commodity Future (far-month) ──
    {
        "SEM_TRADING_SYMBOL": "GOLD OCT FUT",
        "SEM_SMST_SECURITY_ID": "483079",
        "SEM_EXM_EXCH_ID": "MCX_COMM",
        "SEM_INSTRUMENT_NAME": "FUTCOM",
        "SEM_LOT_UNITS": 1,
        "SEM_TICK_SIZE": 1.0,
        "SEM_EXPIRY_DATE": "2026-10-05",
        "SEM_CUSTOM_SYMBOL": "GOLD",
        "SM_SYMBOL_NAME": "GOLD",
    },
    # ── BSE F&O Option (SENSEX) ──
    {
        "SEM_TRADING_SYMBOL": "SENSEX-26Jun2026-80000-CE",
        "SEM_SMST_SECURITY_ID": "70000",
        "SEM_EXM_EXCH_ID": "BSE_FNO",
        "SEM_INSTRUMENT_NAME": "OPTIDX",
        "SEM_LOT_UNITS": 10,
        "SEM_TICK_SIZE": 0.05,
        "SEM_EXPIRY_DATE": "2026-06-26",
        "SEM_STRIKE_PRICE": 80000,
        "SEM_OPTION_TYPE": "CE",
        "SEM_CUSTOM_SYMBOL": "SENSEX 26 JUN 80000 CALL",
        "SM_SYMBOL_NAME": "SENSEX",
    },
    # ── Currency Future (NSE) ──
    {
        "SEM_TRADING_SYMBOL": "USDINR-26Jun2026-FUT",
        "SEM_SMST_SECURITY_ID": "80000",
        "SEM_EXM_EXCH_ID": "NSE_CURRENCY",
        "SEM_INSTRUMENT_NAME": "FUTCUR",
        "SEM_LOT_UNITS": 1000,
        "SEM_TICK_SIZE": 0.0025,
        "SEM_EXPIRY_DATE": "2026-06-26",
        "SEM_CUSTOM_SYMBOL": "USDINR JUN FUT",
        "SM_SYMBOL_NAME": "USDINR",
    },
    # ── Currency Option (NSE) ──
    {
        "SEM_TRADING_SYMBOL": "USDINR-26Jun2026-85-CE",
        "SEM_SMST_SECURITY_ID": "80100",
        "SEM_EXM_EXCH_ID": "NSE_CURRENCY",
        "SEM_INSTRUMENT_NAME": "OPTCUR",
        "SEM_LOT_UNITS": 1000,
        "SEM_TICK_SIZE": 0.0025,
        "SEM_EXPIRY_DATE": "2026-06-26",
        "SEM_STRIKE_PRICE": 85,
        "SEM_OPTION_TYPE": "CE",
        "SEM_CUSTOM_SYMBOL": "USDINR 26 JUN 85 CALL",
        "SM_SYMBOL_NAME": "USDINR",
    },
    # ── Stock F&O Option (RELIANCE) ──
    {
        "SEM_TRADING_SYMBOL": "RELIANCE-26Jun2026-3000-CE",
        "SEM_SMST_SECURITY_ID": "60000",
        "SEM_EXM_EXCH_ID": "NSE_FNO",
        "SEM_INSTRUMENT_NAME": "OPTSTK",
        "SEM_LOT_UNITS": 250,
        "SEM_TICK_SIZE": 0.05,
        "SEM_EXPIRY_DATE": "2026-06-26",
        "SEM_STRIKE_PRICE": 3000,
        "SEM_OPTION_TYPE": "CE",
        "SEM_CUSTOM_SYMBOL": "RELIANCE 26 JUN 3000 CALL",
        "SM_SYMBOL_NAME": "RELIANCE",
    },
    # ── Stock F&O Future (RELIANCE) ──
    {
        "SEM_TRADING_SYMBOL": "RELIANCE-26Jun2026-FUT",
        "SEM_SMST_SECURITY_ID": "60100",
        "SEM_EXM_EXCH_ID": "NSE_FNO",
        "SEM_INSTRUMENT_NAME": "FUTSTK",
        "SEM_LOT_UNITS": 250,
        "SEM_TICK_SIZE": 0.05,
        "SEM_EXPIRY_DATE": "2026-06-26",
        "SEM_CUSTOM_SYMBOL": "RELIANCE JUN FUT",
        "SM_SYMBOL_NAME": "RELIANCE",
    },
]


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_client():
    return FakeHttpClient()


@pytest.fixture
def sample_rows():
    return list(SAMPLE_ROWS)


@pytest.fixture
def resolver(sample_rows):
    r = SymbolResolver()
    r.load_from_rows(sample_rows)
    return r
