"""Unit tests for DhanBrokerFactory and GatewayRegistry singleton behavior."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from brokers.adapters.dhan.compat_gateway import DhanCompatibilityGateway
from brokers.adapters.dhan.factory import DhanBrokerFactory
from brokers.adapters.dhan.gateway import DhanGateway
from brokers.infrastructure.registry import GatewayRegistry


@pytest.fixture(autouse=True)
def _clear_registry():
    GatewayRegistry.clear()
    yield
    GatewayRegistry.clear()


@patch("brokers.adapters.dhan.auth.DhanAuth.get_token", return_value="tok")
@patch("brokers.adapters.dhan.gateway.JsonTokenStateStore")
def test_factory_returns_compat_gateway(_store, _token):
    gw = DhanBrokerFactory.create(access_token="tok", client_id="cid-1")
    assert isinstance(gw, DhanCompatibilityGateway)
    assert isinstance(gw.inner, DhanGateway)
    gw.close()


@patch("brokers.adapters.dhan.auth.DhanAuth.get_token", return_value="tok")
@patch("brokers.adapters.dhan.gateway.JsonTokenStateStore")
def test_factory_singleton_per_client_id(_store, _token):
    gw1 = DhanBrokerFactory.create(access_token="tok", client_id="same-client")
    gw2 = DhanBrokerFactory.create(access_token="tok", client_id="same-client")
    assert gw1 is gw2
    gw1.close()


@patch("brokers.adapters.dhan.auth.DhanAuth.get_token", return_value="tok")
@patch("brokers.adapters.dhan.gateway.JsonTokenStateStore")
def test_factory_distinct_per_client_id(_store, _token):
    gw1 = DhanBrokerFactory.create(access_token="tok", client_id="client-a")
    gw2 = DhanBrokerFactory.create(access_token="tok", client_id="client-b")
    assert gw1 is not gw2
    gw1.close()
    gw2.close()


@patch("brokers.adapters.dhan.auth.DhanAuth.get_token", return_value="tok")
@patch("brokers.adapters.dhan.gateway.JsonTokenStateStore")
def test_factory_builds_gateway_once(_store, _token):
    with patch(
        "brokers.adapters.dhan.factory.DhanGateway",
        wraps=DhanGateway,
    ) as gateway_cls:
        DhanBrokerFactory.create(access_token="tok", client_id="cid")
        DhanBrokerFactory.create(access_token="tok", client_id="cid")
        assert gateway_cls.call_count == 1
    GatewayRegistry.clear()
