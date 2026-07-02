"""Unit tests for OptionsAdapter."""

from decimal import Decimal

from brokers.dhan.options import OptionsAdapter


def test_option_chain_parsing(fake_client, resolver):
    fake_client.set_response(
        "POST",
        "/optionchain",
        {
            "data": {
                "last_price": 24500.0,
                "oc": {
                    "24000": {
                        "ce": {
                            "last_price": 520.0,
                            "oi": 12345,
                            "volume": 6789,
                            "implied_volatility": 14.5,
                            "security_id": "55500",
                            "greeks": {
                                "delta": 0.65,
                                "theta": -12.3,
                                "gamma": 0.0012,
                                "vega": 15.4,
                            },
                        },
                        "pe": {
                            "last_price": 30.0,
                            "oi": 9876,
                            "volume": 4321,
                            "implied_volatility": 15.2,
                            "security_id": "55501",
                            "greeks": {
                                "delta": -0.12,
                                "theta": -8.1,
                                "gamma": 0.0010,
                                "vega": 13.2,
                            },
                        },
                    },
                    "25000": {
                        "ce": {
                            "last_price": 120.0,
                            "oi": 22222,
                            "volume": 11111,
                            "implied_volatility": 13.0,
                            "security_id": "55600",
                            "greeks": {
                                "delta": 0.35,
                                "theta": -10.0,
                                "gamma": 0.0015,
                                "vega": 16.0,
                            },
                        },
                        "pe": {
                            "last_price": 620.0,
                            "oi": 33333,
                            "volume": 22222,
                            "implied_volatility": 16.0,
                            "security_id": "55601",
                            "greeks": {
                                "delta": -0.60,
                                "theta": -14.0,
                                "gamma": 0.0008,
                                "vega": 11.0,
                            },
                        },
                    },
                },
            }
        },
    )
    adapter = OptionsAdapter(fake_client, resolver)
    chain = adapter.get_option_chain("NIFTY", "INDEX", "2026-06-26")

    assert chain["underlying"] == "NIFTY"
    assert chain["expiry"] == "2026-06-26"
    assert chain["spot"] == Decimal("24500.0")
    assert len(chain["strikes"]) == 2

    # Strikes are sorted by price
    s24000 = chain["strikes"][0]
    assert s24000["strike"] == Decimal("24000")
    assert s24000["call"]["ltp"] == Decimal("520.0")
    assert s24000["call"]["oi"] == 12345
    assert s24000["put"]["ltp"] == Decimal("30.0")
    assert s24000["put"]["oi"] == 9876

    s25000 = chain["strikes"][1]
    assert s25000["strike"] == Decimal("25000")
    assert s25000["call"]["security_id"] == "55600"
    assert s25000["put"]["security_id"] == "55601"


def test_option_chain_mcx_direct(fake_client, resolver):
    fake_client.set_response(
        "POST",
        "/optionchain",
        {
            "data": {
                "last_price": 72000.0,
                "oc": {
                    "72000": {
                        "ce": {"last_price": 1500.0, "oi": 100, "volume": 50, "greeks": {}},
                        "pe": {"last_price": 1400.0, "oi": 80, "volume": 40, "greeks": {}},
                    },
                },
            }
        },
    )
    adapter = OptionsAdapter(fake_client, resolver)
    chain = adapter.get_option_chain("GOLD", "MCX", "2026-08-05", security_id=114)

    # Verify the request was made with MCX_COMM segment and the direct security_id
    payloads = fake_client.calls_for("POST", "/optionchain")
    assert len(payloads) == 1
    payload = payloads[0]
    assert payload["UnderlyingScrip"] == 114
    assert payload["UnderlyingSeg"] == "MCX_COMM"
    assert chain["spot"] == Decimal("72000.0")


def test_get_expiries(fake_client, resolver):
    fake_client.set_response(
        "POST",
        "/optionchain/expirylist",
        {"data": {"expiryList": ["2026-06-26", "2026-07-31", "2026-08-28"]}},
    )
    adapter = OptionsAdapter(fake_client, resolver)
    expiries = adapter.get_expiries("NIFTY", "INDEX")
    assert expiries == ["2026-06-26", "2026-07-31", "2026-08-28"]


def test_option_chain_greeks_extracted(fake_client, resolver):
    fake_client.set_response(
        "POST",
        "/optionchain",
        {
            "data": {
                "last_price": 24500.0,
                "oc": {
                    "24500": {
                        "ce": {
                            "last_price": 300.0,
                            "oi": 5000,
                            "volume": 2000,
                            "greeks": {
                                "delta": 0.52,
                                "theta": -11.5,
                                "gamma": 0.0014,
                                "vega": 14.8,
                            },
                        },
                        "pe": {
                            "last_price": 280.0,
                            "oi": 4500,
                            "volume": 1800,
                            "greeks": {
                                "delta": -0.48,
                                "theta": -10.2,
                                "gamma": 0.0013,
                                "vega": 13.9,
                            },
                        },
                    },
                },
            }
        },
    )
    adapter = OptionsAdapter(fake_client, resolver)
    chain = adapter.get_option_chain("NIFTY", "INDEX", "2026-06-26")

    strike = chain["strikes"][0]
    # Verify all greek keys are present in call
    call = strike["call"]
    assert "delta" in call
    assert "theta" in call
    assert "gamma" in call
    assert "vega" in call
    assert call["delta"] == Decimal("0.52")
    assert call["theta"] == Decimal("-11.5")
    assert call["gamma"] == Decimal("0.0014")
    assert call["vega"] == Decimal("14.8")

    # Verify all greek keys are present in put
    put = strike["put"]
    assert "delta" in put
    assert "theta" in put
    assert "gamma" in put
    assert "vega" in put
    assert put["delta"] == Decimal("-0.48")
    assert put["theta"] == Decimal("-10.2")
