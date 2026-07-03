"""Unit tests for DhanBrokerFactory and GatewayRegistry singleton behavior."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from brokers.adapters.dhan.factory import DhanBrokerFactory, gateway_registry
from brokers.adapters.dhan.gateway import DhanGateway


@pytest.fixture(autouse=True)
def _clear_registry():
    gateway_registry.clear()
    yield
    gateway_registry.clear()


@patch("brokers.adapters.dhan.auth.DhanAuth.get_token", return_value="tok")
@patch("brokers.infrastructure.storage.token_store.JsonTokenStateStore")
def test_factory_returns_gateway(_store, _token):
    gw = DhanBrokerFactory.create(access_token="tok", client_id="cid-1")
    assert isinstance(gw, DhanGateway)
    gw.close()


@patch("brokers.adapters.dhan.auth.DhanAuth.get_token", return_value="tok")
@patch("brokers.infrastructure.storage.token_store.JsonTokenStateStore")
def test_factory_singleton_per_client_id(_store, _token):
    gw1 = DhanBrokerFactory.create(access_token="tok", client_id="same-client")
    gw2 = DhanBrokerFactory.create(access_token="tok", client_id="same-client")
    assert gw1 is gw2
    gw1.close()


@patch("brokers.adapters.dhan.auth.DhanAuth.get_token", return_value="tok")
@patch("brokers.infrastructure.storage.token_store.JsonTokenStateStore")
def test_factory_distinct_per_client_id(_store, _token):
    gw1 = DhanBrokerFactory.create(access_token="tok", client_id="client-a")
    gw2 = DhanBrokerFactory.create(access_token="tok", client_id="client-b")
    assert gw1 is not gw2
    gw1.close()
    gw2.close()


@patch("brokers.adapters.dhan.auth.DhanAuth.get_token", return_value="tok")
@patch("brokers.infrastructure.storage.token_store.JsonTokenStateStore")
def test_factory_builds_gateway_once(_store, _token):
    with patch(
        "brokers.adapters.dhan.factory.DhanGateway",
        wraps=DhanGateway,
    ) as gateway_cls:
        DhanBrokerFactory.create(access_token="tok", client_id="cid")
        DhanBrokerFactory.create(access_token="tok", client_id="cid")
        assert gateway_cls.call_count == 1
    gateway_registry.clear()
