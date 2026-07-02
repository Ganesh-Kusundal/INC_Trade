"""Unit tests for brokers.common.options — chain normalizer and facade."""

from __future__ import annotations

from decimal import Decimal

from brokers.common.options.chain_normalizer import (
    to_canonical_strikes,
    upstox_chain_to_canonical,
)
from domain.entities import OptionChain, OptionContract
from domain.entities.options import OptionLeg, OptionStrike


def _row(strike: str, ce_ltp=100, pe_ltp=80, ce_iv=14, pe_iv=15) -> dict:
    return {
        "strike": strike,
        "call": {
            "ltp": ce_ltp,
            "oi": 1000,
            "volume": 500,
            "iv": ce_iv,
            "symbol": "NIFTY" + strike + "CE",
            "security_id": strike + "C",
        },
        "put": {
            "ltp": pe_ltp,
            "oi": 800,
            "volume": 400,
            "iv": pe_iv,
            "symbol": "NIFTY" + strike + "PE",
            "security_id": strike + "P",
        },
    }


def test_to_canonical_from_dhan_dict():
    rows = [_row("24500"), _row("24600", ce_ltp=120, pe_ltp=90)]
    strikes = to_canonical_strikes(rows)
    assert len(strikes) == 2
    assert strikes[0]["strike"] == Decimal("24500")
    assert strikes[0]["call"]["ltp"] == 100
    assert strikes[0]["put"]["symbol"] == "NIFTY24500PE"
    assert strikes[1]["call"]["ltp"] == 120


def test_to_canonical_from_option_contract():
    contracts = [
        OptionContract(strike=Decimal("24500"), call_ltp=Decimal("100"), put_ltp=Decimal("80")),
    ]
    strikes = to_canonical_strikes(contracts)
    assert len(strikes) == 1
    assert strikes[0]["strike"] == Decimal("24500")
    assert strikes[0]["call"]["ltp"] == Decimal("100")
    # No symbol/instrument_key in flat contract form.
    assert strikes[0]["call"]["symbol"] is None
    assert strikes[0]["call"]["instrument_key"] is None


def test_to_canonical_handles_ce_pe_legacy_keys():
    """Dhan legacy chain dicts may still use CE/PE upper-case keys."""
    rows = [
        {
            "strikePrice": "24500",
            "CE": {"tradingSymbol": "NIFTY24500CE", "last_price": "100"},
            "PE": {"tradingSymbol": "NIFTY24500PE", "last_price": "80"},
        }
    ]
    strikes = to_canonical_strikes(rows)
    assert len(strikes) == 1
    assert strikes[0]["strike"] == Decimal("24500")
    assert strikes[0]["call"]["trading_symbol"] == "NIFTY24500CE"
    assert strikes[0]["put"]["trading_symbol"] == "NIFTY24500PE"


def test_upstox_chain_to_canonical_recovers_per_leg_keys():
    raw = [
        {
            "strike_price": 24500,
            "expiry": "2026-06-26",
            "call_options": {
                "market_data": {"ltp": 100, "oi": 1000, "volume": 500, "iv": 14},
                "instrument_key": "NSE_FO|123",
                "trading_symbol": "NIFTY24500CE",
            },
            "put_options": {
                "market_data": {"ltp": 80, "oi": 800, "volume": 400, "iv": 15},
                "instrument_key": "NSE_FO|124",
                "trading_symbol": "NIFTY24500PE",
            },
        }
    ]
    contracts = [
        OptionContract(
            strike=Decimal("24500"),
            expiry="2026-06-26",
            call_ltp=Decimal("100"),
            put_ltp=Decimal("80"),
            call_oi=1000,
            put_oi=800,
            call_volume=500,
            put_volume=400,
            call_iv=Decimal("14"),
            put_iv=Decimal("15"),
        )
    ]
    out = upstox_chain_to_canonical(contracts, raw, "NIFTY", "NFO", "2026-06-26")
    assert isinstance(out, OptionChain)
    assert out.underlying == "NIFTY"
    assert out.exchange == "NFO"
    assert out.expiry == "2026-06-26"
    assert len(out.strikes) == 1
    call = out.strikes[0].call
    put = out.strikes[0].put
    assert call.trading_symbol == "NIFTY24500CE"
    assert call.instrument_key == "NSE_FO|123"
    assert call.ltp == Decimal("100")
    assert call.oi == 1000
    assert put.trading_symbol == "NIFTY24500PE"
    assert put.instrument_key == "NSE_FO|124"


def test_upstox_chain_to_canonical_handles_missing_raw():
    """If raw_rows is None, per-leg symbol fields are None — LTP still flows."""
    contracts = [OptionContract(strike=Decimal("24500"), call_ltp=Decimal("50"))]
    out = upstox_chain_to_canonical(contracts, None, "NIFTY", "NFO", "2026-06-26")
    assert out.strikes[0].call.ltp == Decimal("50")
    assert out.strikes[0].call.trading_symbol is None


def test_option_chain_dict_roundtrip():
    payload = {
        "underlying": "NIFTY",
        "exchange": "NFO",
        "expiry": "2026-06-26",
        "spot": "24500",
        "strikes": [_row("24500")],
    }
    chain = OptionChain.from_dict(payload)
    restored = OptionChain.from_dict(chain.to_dict())
    assert restored.underlying == "NIFTY"
    assert len(restored.strikes) == 1
    assert restored.strikes[0].strike == Decimal("24500")


def test_option_leg_from_dict_nested_greeks():
    """OptionLeg.from_dict must parse greeks from nested dict."""
    data = {
        "ltp": 100,
        "oi": 5000,
        "volume": 2000,
        "iv": 14.5,
        "greeks": {"delta": 0.52, "theta": -11.5, "gamma": 0.0014, "vega": 14.8},
    }
    leg = OptionLeg.from_dict(data)
    assert leg.ltp == Decimal("100")
    assert leg.greeks is not None
    assert leg.greeks["delta"] == 0.52
    assert leg.greeks["theta"] == -11.5
    assert leg.greeks["gamma"] == 0.0014
    assert leg.greeks["vega"] == 14.8


def test_option_leg_from_dict_flat_greeks():
    """OptionLeg.from_dict must parse greeks from flat top-level keys (Dhan adapter format)."""
    data = {
        "ltp": 300,
        "oi": 5000,
        "volume": 2000,
        "iv": 15.0,
        "delta": 0.52,
        "theta": -11.5,
        "gamma": 0.0014,
        "vega": 14.8,
    }
    leg = OptionLeg.from_dict(data)
    assert leg.ltp == Decimal("300")
    assert leg.greeks is not None
    assert leg.greeks["delta"] == 0.52
    assert leg.greeks["theta"] == -11.5
    assert leg.greeks["gamma"] == 0.0014
    assert leg.greeks["vega"] == 14.8


def test_option_leg_from_dict_no_greeks():
    """OptionLeg.from_dict returns greeks=None when no greek data present."""
    data = {"ltp": 50, "oi": 1000}
    leg = OptionLeg.from_dict(data)
    assert leg.ltp == Decimal("50")
    assert leg.greeks is None


def test_option_strike_from_dict_preserves_greeks():
    """Full round-trip: adapter dict -> OptionStrike -> greeks preserved."""
    data = {
        "strike": "24500",
        "call": {
            "ltp": 300,
            "oi": 5000,
            "volume": 2000,
            "iv": 15.0,
            "delta": 0.52,
            "theta": -11.5,
            "gamma": 0.0014,
            "vega": 14.8,
        },
        "put": {
            "ltp": 280,
            "oi": 4500,
            "volume": 1800,
            "iv": 14.0,
            "delta": -0.48,
            "theta": -10.2,
            "gamma": 0.0013,
            "vega": 13.9,
        },
    }
    strike = OptionStrike.from_dict(data)
    assert strike.strike == Decimal("24500")
    assert strike.call.greeks["delta"] == 0.52
    assert strike.put.greeks["delta"] == -0.48
    assert strike.call.greeks["vega"] == 14.8
    assert strike.put.greeks["theta"] == -10.2
