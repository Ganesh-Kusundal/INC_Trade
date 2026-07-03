"""Symbol mapping parity — forward lookup variants."""

from __future__ import annotations

from brokers.adapters.dhan.identity import DhanInstrumentResolver

SAMPLE_CSV = (
    "SEM_TRADING_SYMBOL,SEM_SMST_SECURITY_ID,SEM_EXM_EXCH_ID,SEM_INSTRUMENT_NAME,"
    "SEM_LOT_UNITS,SEM_OPTION_TYPE,SM_SYMBOL_NAME\n"
    "RELIANCE,2885,NSE,EQUITY,1,,RELIANCE\n"
    "NIFTY 26 JUN 25000 CE,55000,NSE,OPTIDX,25,CE,NIFTY\n"
    "NIFTY 26 JUN FUT,51976,NSE,FUTIDX,25,,NIFTY\n"
)


def _resolver() -> DhanInstrumentResolver:
    r = DhanInstrumentResolver()
    r.load_from_csv_text(SAMPLE_CSV)
    return r


def test_equity_forward():
    ref = _resolver().resolve("RELIANCE", "NSE")
    assert ref.security_id == "2885"


def test_option_ce_forward():
    ref = _resolver().resolve("NIFTY 26 JUN 25000 CE", "NFO")
    assert ref.security_id == "55000"


def test_option_call_suffix():
    ref = _resolver().resolve("NIFTY 26 JUN 25000 CALL", "NFO")
    assert ref.security_id == "55000"


def test_futures_by_underlying_index():
    refs = _resolver().get_futures("NIFTY", "NFO")
    assert any(r.security_id == "51976" for r in refs)
