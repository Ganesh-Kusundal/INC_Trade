"""Unit tests for FuturesAdapter."""

from brokers.dhan.futures import FuturesAdapter


def test_get_contracts_from_cache(fake_client, resolver):
    adapter = FuturesAdapter(fake_client, resolver)
    contracts = adapter.get_contracts("GOLD", "MCX")
    # Sample data has two GOLD futures: AUG and OCT
    assert len(contracts) == 2
    # Contracts are sorted by expiry; AUG comes before OCT
    assert contracts[0]["expiry"] == "2026-08-05"
    assert contracts[0]["security_id"] == "466583"
    assert contracts[0]["underlying"] == "GOLD"
    assert contracts[0]["exchange"] == "MCX"
    assert contracts[1]["expiry"] == "2026-10-05"
    assert contracts[1]["security_id"] == "483079"


def test_get_nearest_returns_first(fake_client, resolver):
    adapter = FuturesAdapter(fake_client, resolver)
    nearest = adapter.get_nearest("GOLD", "MCX")
    assert nearest is not None
    assert nearest["expiry"] == "2026-08-05"
    assert nearest["security_id"] == "466583"


def test_get_nearest_returns_none_for_unknown(fake_client, resolver):
    adapter = FuturesAdapter(fake_client, resolver)
    nearest = adapter.get_nearest("UNKNOWN", "MCX")
    assert nearest is None


def test_is_commodity(fake_client, resolver):
    adapter = FuturesAdapter(fake_client, resolver)
    assert adapter.is_commodity("GOLD") is True
    assert adapter.is_commodity("SILVER") is True
    assert adapter.is_commodity("CRUDEOIL") is True
    assert adapter.is_commodity("RELIANCE") is False
    assert adapter.is_commodity("NIFTY") is False


def test_get_expiries(fake_client, resolver):
    adapter = FuturesAdapter(fake_client, resolver)
    expiries = adapter.get_expiries("GOLD", "MCX")
    # Expiries are sorted and unique
    assert expiries == ["2026-08-05", "2026-10-05"]
    assert len(expiries) == len(set(expiries))  # all unique
