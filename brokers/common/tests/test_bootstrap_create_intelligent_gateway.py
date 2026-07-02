from __future__ import annotations

from types import SimpleNamespace

import pytest


@pytest.fixture
def fake_infra():
    return SimpleNamespace()


@pytest.fixture
def bootstrap_calls(monkeypatch, fake_infra):
    calls: dict[str, object] = {}

    async def _fake_bootstrap(gateways, *, policy=None):
        calls["gateways"] = gateways
        calls["policy"] = policy
        return fake_infra

    monkeypatch.setattr(
        "brokers.common.bootstrap.bootstrap_from_gateways",
        _fake_bootstrap,
    )
    return calls


@pytest.mark.asyncio
async def test_defaults_primary_broker_to_first_gateway_when_only_upstox_is_provided(
    bootstrap_calls,
):
    from brokers.common.bootstrap import create_intelligent_gateway

    gateway = object()

    result = await create_intelligent_gateway(
        [("upstox", gateway)],
        smart=True,
    )

    assert result.smart_mode is True
    assert result.primary_broker == "upstox"
    assert bootstrap_calls["gateways"] == [("upstox", gateway)]
