"""Regression tests for UpstoxBrokerFactory TOTP scheduler wiring."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import MagicMock, patch

import pytest

from brokers.upstox.auth.config import UpstoxConnectionSettings
from brokers.upstox.auth.exceptions import UpstoxAuthError
from brokers.upstox.factory import UpstoxBrokerFactory
from infrastructure.lifecycle import LifecycleManager


def _totp_settings() -> UpstoxConnectionSettings:
    return UpstoxConnectionSettings(
        client_id="up-client",
        access_token="access",
        auth_mode="TOTP",
        mobile="9999999999",
        pin="1234",
        totp_secret="JBSWY3DPEHPK3PXP",
        totp_refresh_hour=7,
        totp_refresh_minute=30,
    )


def _static_settings() -> UpstoxConnectionSettings:
    return UpstoxConnectionSettings(
        client_id="up-client",
        access_token="access",
        auth_mode="STATIC",
    )


def _run_factory(*, settings: UpstoxConnectionSettings, lifecycle: LifecycleManager) -> None:
    mock_broker = MagicMock()
    mock_broker.token_manager = MagicMock()
    mock_broker.market_data_websocket = MagicMock()
    mock_broker.portfolio_stream = MagicMock()
    mock_broker.connect.return_value = True

    with (
        patch(
            "brokers.upstox.factory.UpstoxSettingsLoader.from_env",
            return_value=settings,
        ),
        patch(
            "brokers.upstox.factory.UpstoxBroker",
            return_value=mock_broker,
        ),
        patch(
            "brokers.upstox.factory.UpstoxBrokerGateway",
        ) as gateway_cls,
    ):
        gateway_cls.return_value = MagicMock()
        UpstoxBrokerFactory().create(
            lifecycle=lifecycle,
            load_instruments=False,
        )


class TestUpstoxFactoryTotpScheduler:
    def test_registers_totp_scheduler_when_auth_mode_totp(self):
        lifecycle = LifecycleManager()
        _run_factory(settings=_totp_settings(), lifecycle=lifecycle)
        assert "upstox.totp_refresh_scheduler" in lifecycle.service_names()

    def test_skips_totp_scheduler_for_static_auth(self):
        lifecycle = LifecycleManager()
        _run_factory(settings=_static_settings(), lifecycle=lifecycle)
        assert "upstox.totp_refresh_scheduler" not in lifecycle.service_names()

    def test_registers_websocket_services_with_lifecycle(self):
        lifecycle = LifecycleManager()
        _run_factory(settings=_static_settings(), lifecycle=lifecycle)
        names = lifecycle.service_names()
        assert "upstox.websocket" in names
        assert "upstox.portfolio_stream" in names

    def test_analytics_only_does_not_block_totp_scheduler(self):
        lifecycle = LifecycleManager()
        settings = replace(_totp_settings(), analytics_only=True)
        _run_factory(settings=settings, lifecycle=lifecycle)
        assert "upstox.totp_refresh_scheduler" in lifecycle.service_names()

    def test_totp_connect_failure_raises_auth_error(self):
        lifecycle = LifecycleManager()
        mock_broker = MagicMock()
        mock_broker.token_manager = MagicMock()
        mock_broker.market_data_websocket = MagicMock()
        mock_broker.portfolio_stream = MagicMock()
        mock_broker.connect.return_value = False

        with (
            patch(
                "brokers.upstox.factory.UpstoxSettingsLoader.from_env",
                return_value=_totp_settings(),
            ),
            patch(
                "brokers.upstox.factory.UpstoxBroker",
                return_value=mock_broker,
            ),
            pytest.raises(UpstoxAuthError, match="TOTP bootstrap failed"),
        ):
            UpstoxBrokerFactory().create(
                lifecycle=lifecycle,
                load_instruments=False,
            )

    def test_late_registered_scheduler_starts_after_start_all(self):
        lifecycle = LifecycleManager()
        lifecycle.start_all()
        _run_factory(settings=_totp_settings(), lifecycle=lifecycle)
        scheduler = lifecycle.get("upstox.totp_refresh_scheduler")
        assert scheduler is not None
        assert scheduler.is_running is True
