"""Unit tests for IPManagementAdapter."""

import pytest

from brokers.dhan.ip_management import IPManagementAdapter


def test_set_ip_primary(fake_client):
    """Verify POST /ip with PRIMARY type."""
    fake_client.set_response("POST", "/ip", {"status": "success"})
    adapter = IPManagementAdapter(fake_client)
    result = adapter.set_ip("192.168.1.100", "PRIMARY")

    payloads = fake_client.calls_for("POST", "/ip")
    assert len(payloads) == 1
    payload = payloads[0]
    assert payload["ipAddress"] == "192.168.1.100"
    assert payload["ipType"] == "PRIMARY"
    assert result["status"] == "success"


def test_set_ip_secondary(fake_client):
    """Verify POST /ip with SECONDARY type."""
    fake_client.set_response("POST", "/ip", {"status": "success"})
    adapter = IPManagementAdapter(fake_client)
    adapter.set_ip("10.0.0.1", "SECONDARY")

    payloads = fake_client.calls_for("POST", "/ip")
    assert len(payloads) == 1
    payload = payloads[0]
    assert payload["ipType"] == "SECONDARY"


def test_modify_ip(fake_client):
    """Verify PUT /ip."""
    fake_client.set_response("PUT", "/ip", {"status": "success"})
    adapter = IPManagementAdapter(fake_client)
    adapter.modify_ip("192.168.1.200", "PRIMARY")

    payloads = fake_client.calls_for("PUT", "/ip")
    assert len(payloads) == 1
    payload = payloads[0]
    assert payload["ipAddress"] == "192.168.1.200"
    assert payload["ipType"] == "PRIMARY"


def test_get_ip(fake_client):
    """Verify GET /ip response parsing."""
    fake_client.set_response(
        "GET",
        "/ip",
        {
            "data": [
                {
                    "ipAddress": "192.168.1.100",
                    "ipType": "PRIMARY",
                    "status": "ACTIVE",
                },
                {
                    "ipAddress": "10.0.0.1",
                    "ipType": "SECONDARY",
                    "status": "INACTIVE",
                },
            ]
        },
    )
    adapter = IPManagementAdapter(fake_client)
    configs = adapter.get_ip()

    assert len(configs) == 2
    assert configs[0].ip_address == "192.168.1.100"
    assert configs[0].ip_type == "PRIMARY"
    assert configs[0].status == "ACTIVE"
    assert configs[1].ip_type == "SECONDARY"


def test_set_ip_validation(fake_client):
    """Verify valid IP format."""
    adapter = IPManagementAdapter(fake_client)

    with pytest.raises(ValueError) as exc_info:
        adapter.set_ip("invalid-ip", "PRIMARY")
    assert "ip" in str(exc_info.value).lower()
