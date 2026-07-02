"""Verify Upstox extended adapters load lazily."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from brokers.upstox.auth.config import UpstoxConnectionSettings
from brokers.upstox.broker import UpstoxBroker


@pytest.fixture
def broker() -> UpstoxBroker:
    settings = UpstoxConnectionSettings(client_id="test-client")
    with patch.object(UpstoxBroker, "connect", return_value=True):
        return UpstoxBroker(settings=settings, token_manager=MagicMock())


def test_core_bootstrap_does_not_import_extended_modules(broker: UpstoxBroker) -> None:
    assert not broker._extended_ready
    assert not hasattr(broker, "ipo")
    assert not hasattr(broker, "payments")


def test_ensure_extended_loads_ipo_adapter(broker: UpstoxBroker) -> None:
    broker._ensure_extended()
    assert broker._extended_ready
    assert hasattr(broker, "ipo")
