"""Shared test fixtures for environment-aware broker testing.

These fixtures provide standardized broker configurations for:
- Sandbox testing (write operations)
- Live read-only testing (market data, quotes, historical)
- Split environment testing (reads from live, writes to sandbox)

Usage:
    from brokers.common.tests.conftest import sandbox_broker_settings

    @pytest.mark.sandbox
    def test_place_order(sandbox_broker_settings):
        # Test uses sandbox configuration
        pass
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def sandbox_broker_settings():
    """Broker settings configured for sandbox environment.

    Returns settings with:
    - environment=SANDBOX
    - allow_live_orders=False (safe default)
    - Sandbox URLs configured
    """

    # Return dict that can be used to construct either broker settings
    return {
        "environment": "SANDBOX",
        "allow_live_orders": False,
        "analytics_only": False,
    }


@pytest.fixture
def live_read_broker_settings():
    """Broker settings for live read-only operations.

    Returns settings with:
    - environment=LIVE
    - allow_live_orders=False (read-only mode)
    - Live URLs configured
    """
    return {
        "environment": "LIVE",
        "allow_live_orders": False,
        "analytics_only": True,  # Read-only mode
    }


@pytest.fixture
def live_write_broker_settings():
    """Broker settings for live environment with order execution.

    Returns settings with:
    - environment=LIVE
    - allow_live_orders=True (explicit opt-in for live orders)
    - Live URLs configured

    WARNING: This fixture enables live order execution. Use with caution.
    """
    return {
        "environment": "LIVE",
        "allow_live_orders": True,
        "analytics_only": False,
    }


@pytest.fixture
def mock_sandbox_gateway(sandbox_broker_settings):
    """Mock gateway configured for sandbox environment.

    Creates a mock broker gateway with sandbox settings.
    All write operations will be routed to sandbox endpoints.
    """
    gateway = MagicMock()
    gateway.settings = MagicMock(**sandbox_broker_settings)
    gateway.settings.is_sandbox = True
    gateway.settings.is_live = False
    return gateway


@pytest.fixture
def mock_live_read_gateway(live_read_broker_settings):
    """Mock gateway for live read-only operations.

    Creates a mock broker gateway with live settings but read-only mode.
    Read operations will use live endpoints.
    Write operations will be blocked.
    """
    gateway = MagicMock()
    gateway.settings = MagicMock(**live_read_broker_settings)
    gateway.settings.is_sandbox = False
    gateway.settings.is_live = True
    return gateway


@pytest.fixture
def mock_live_write_gateway(live_write_broker_settings):
    """Mock gateway for live environment with order execution.

    Creates a mock broker gateway with live settings and order execution enabled.

    WARNING: This enables live order execution in tests. Use with caution.
    """
    gateway = MagicMock()
    gateway.settings = MagicMock(**live_write_broker_settings)
    gateway.settings.is_sandbox = False
    gateway.settings.is_live = True
    return gateway
