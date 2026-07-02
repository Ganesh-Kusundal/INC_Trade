"""Unit tests for EDISAdapter."""

import pytest

from brokers.dhan.edis import EDISAdapter


def test_generate_tpin(fake_client):
    """Verify POST /edis/tpin."""
    fake_client.set_response("POST", "/edis/tpin", {"status": "success", "tpin": "123456"})
    adapter = EDISAdapter(fake_client)
    result = adapter.generate_tpin()

    payloads = fake_client.calls_for("POST", "/edis/tpin")
    assert len(payloads) == 1
    assert result["status"] == "success"
    assert "tpin" in result


def test_authorize_edis(fake_client):
    """Verify POST /edis/authorize with ISIN, qty, exchange."""
    fake_client.set_response(
        "POST",
        "/edis/authorize",
        {
            "status": "success",
            "authId": "AUTH123",
        },
    )
    adapter = EDISAdapter(fake_client)
    result = adapter.authorize_edis("INE002A01018", 10, "NSE")

    payloads = fake_client.calls_for("POST", "/edis/authorize")
    assert len(payloads) == 1
    payload = payloads[0]
    assert payload["isin"] == "INE002A01018"
    assert payload["quantity"] == 10
    assert payload["exchange"] == "NSE"
    assert result["status"] == "success"


def test_check_edis_status(fake_client):
    """Verify GET /edis/status/{isin}."""
    fake_client.set_response(
        "GET",
        "/edis/status/INE002A01018",
        {
            "data": {
                "isin": "INE002A01018",
                "status": "AUTHORIZED",
                "quantity": 10,
            }
        },
    )
    adapter = EDISAdapter(fake_client)
    result = adapter.check_status("INE002A01018")

    calls = fake_client.calls_for("GET", "/edis/status/INE002A01018")
    assert len(calls) == 1
    assert result["isin"] == "INE002A01018"
    assert result["status"] == "AUTHORIZED"


def test_generate_tpin_validation(fake_client):
    """Verify ISIN format."""
    adapter = EDISAdapter(fake_client)

    with pytest.raises(ValueError) as exc_info:
        adapter.authorize_edis("INVALID", 10, "NSE")
    assert "isin" in str(exc_info.value).lower()
