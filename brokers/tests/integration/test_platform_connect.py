"""Integration tests for Platform.connect() — auto-login wiring."""
from __future__ import annotations
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from brokers.platform import Platform

def _mock_dhan_creds(*, access_token: str = "", totp: bool = False) -> MagicMock:
    creds = MagicMock()
    creds.client_id = "test-client"
    creds.access_token = access_token
    creds.has_totp = totp
    creds.totp_secret = "SECRET" if totp else ""
    creds.pin = "1234" if totp else ""
    return creds

def _mock_upstox_creds(*, access_token: str = "", totp: bool = False) -> MagicMock:
    creds = MagicMock()
    creds.client_id = "test-client"
    creds.access_token = access_token
    creds.api_key = "test-key"
    creds.has_totp = totp
    creds.totp_secret = "SECRET" if totp else ""
    creds.pin = "1234" if totp else ""
    creds.mobile = "9999999999" if totp else ""
    return creds

class TestPlatformConnectPaper:
    def test_connect_paper(self):
        platform = Platform.paper()
        assert platform.broker_id == "paper"
        assert platform.is_connected is False

class TestPlatformConnectDhan:
    @pytest.mark.asyncio
    async def test_connect_dhan_static_token(self):
        mock_creds = _mock_dhan_creds(access_token="test-token-123")
        with patch(
            "brokers.common.auth.credential_resolver.CredentialResolver.for_dhan",
            return_value=mock_creds,
        ):
            platform = await Platform.connect("dhan")
        assert platform.broker_id == "dhan"
        assert platform._token_scheduler is None

    @pytest.mark.asyncio
    async def test_connect_dhan_totp_path(self):
        mock_creds = _mock_dhan_creds(access_token="", totp=True)
        mock_auth_manager = MagicMock()
        mock_auth_manager.access_token = "fresh-token"
        mock_auth_manager.ensure_valid = MagicMock()
        mock_auth_manager.register_token_receiver = MagicMock()
        mock_auth_manager.state = None
        with patch(
            "brokers.common.auth.credential_resolver.CredentialResolver.for_dhan",
            return_value=mock_creds,
        ), patch(
            "brokers.common.auth.token_manager.AuthManager",
            return_value=mock_auth_manager,
        ), patch(
            "brokers.common.auth.token_scheduler.BackgroundTokenScheduler"
        ) as mock_scheduler_cls:
            mock_scheduler = MagicMock()
            mock_scheduler_cls.return_value = mock_scheduler
            platform = await Platform.connect("dhan")
        assert platform.broker_id == "dhan"
        assert platform._token_scheduler is mock_scheduler
        mock_scheduler.start.assert_called_once()
        mock_auth_manager.ensure_valid.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_dhan_no_credentials_raises(self):
        mock_creds = _mock_dhan_creds(access_token="", totp=False)
        with patch(
            "brokers.common.auth.credential_resolver.CredentialResolver.for_dhan",
            return_value=mock_creds,
        ):
            with pytest.raises(ValueError, match="TOTP_SECRET.*PIN.*required"):
                await Platform.connect("dhan")

class TestPlatformConnectUpstox:
    @pytest.mark.asyncio
    async def test_connect_upstox_static_token(self):
        mock_creds = _mock_upstox_creds(access_token="upstox-token-123")
        with patch(
            "brokers.common.auth.credential_resolver.CredentialResolver.for_upstox",
            return_value=mock_creds,
        ):
            platform = await Platform.connect("upstox")
        assert platform.broker_id == "upstox"
        assert platform._token_scheduler is None

    @pytest.mark.asyncio
    async def test_connect_upstox_totp_path(self):
        mock_creds = _mock_upstox_creds(access_token="", totp=True)
        mock_auth_manager = MagicMock()
        mock_auth_manager.access_token = "fresh-upstox-token"
        mock_auth_manager.ensure_valid = MagicMock()
        mock_auth_manager.register_token_receiver = MagicMock()
        mock_auth_manager.state = None
        with patch(
            "brokers.common.auth.credential_resolver.CredentialResolver.for_upstox",
            return_value=mock_creds,
        ), patch(
            "brokers.common.auth.token_manager.AuthManager",
            return_value=mock_auth_manager,
        ), patch(
            "brokers.common.auth.token_scheduler.BackgroundTokenScheduler"
        ) as mock_scheduler_cls:
            mock_scheduler = MagicMock()
            mock_scheduler_cls.return_value = mock_scheduler
            platform = await Platform.connect("upstox")
        assert platform.broker_id == "upstox"
        assert platform._token_scheduler is mock_scheduler

    @pytest.mark.asyncio
    async def test_connect_upstox_no_credentials_raises(self):
        mock_creds = _mock_upstox_creds(access_token="", totp=False)
        with patch(
            "brokers.common.auth.credential_resolver.CredentialResolver.for_upstox",
            return_value=mock_creds,
        ):
            with pytest.raises(ValueError, match="UPSTOX_ACCESS_TOKEN"):
                await Platform.connect("upstox")

class TestPlatformConnectUnknown:
    @pytest.mark.asyncio
    async def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            await Platform.connect("unknown_broker")

class TestPlatformDisconnect:
    @pytest.mark.asyncio
    async def test_disconnect_stops_scheduler(self):
        platform = Platform.paper()
        mock_scheduler = MagicMock()
        platform._token_scheduler = mock_scheduler
        await platform.disconnect()
        mock_scheduler.stop.assert_called_once()
        assert platform._token_scheduler is None

    @pytest.mark.asyncio
    async def test_disconnect_without_scheduler(self):
        platform = Platform.paper()
        await platform.disconnect()
