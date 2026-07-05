"""Unit tests for DhanAuth TOTP cooldown integration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from brokers.adapters.dhan.auth import DhanAuth
from inc_trade.domain.exceptions import TokenRateLimitError
from inc_trade.infrastructure.totp_cooldown import TOTPCooldown


@pytest.fixture(autouse=True)
def _reset_cooldown(tmp_path):
    TOTPCooldown._instances.clear()
    yield
    TOTPCooldown._instances.clear()


class TestDhanAuthTotpCooldown:
    @patch("brokers.adapters.dhan.auth.requests.post")
    @patch("pyotp.TOTP")
    def test_proactive_cooldown_blocks_second_call(
        self, mock_totp_cls, mock_post, tmp_path
    ):
        mock_totp_cls.return_value.now.return_value = "123456"
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"data": {"accessToken": "tok1"}},
            text="",
        )
        cooldown = TOTPCooldown("dhan-test", state_path=tmp_path / "cd.json")
        auth = DhanAuth(
            access_token="existing",
            client_id="c1",
            pin="1234",
            totp_secret="JBSWY3DPEHPK3PXP",
            totp_cooldown=cooldown,
        )
        auth.generate_token()
        with pytest.raises(TokenRateLimitError, match="cooldown"):
            auth.generate_token()

    @patch("brokers.adapters.dhan.auth.requests.post")
    @patch("pyotp.TOTP")
    def test_broker_rate_limit_records_cooldown(
        self, mock_totp_cls, mock_post, tmp_path
    ):
        mock_totp_cls.return_value.now.return_value = "123456"
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "status": "error",
                "message": "Token can be generated once every 2 minutes",
            },
            text="",
        )
        cooldown = TOTPCooldown("dhan-test2", state_path=tmp_path / "cd2.json")
        auth = DhanAuth(
            access_token="existing",
            client_id="c1",
            pin="1234",
            totp_secret="JBSWY3DPEHPK3PXP",
            totp_cooldown=cooldown,
        )
        with pytest.raises(TokenRateLimitError):
            auth.generate_token()
