from __future__ import annotations

from unittest.mock import MagicMock, patch

from brokers.adapters.upstox.auth.config import UpstoxConnectionSettings
from brokers.adapters.upstox.auth.login import build_auth_url


class TestLoginModule:
    def test_build_auth_url(self):
        s = UpstoxConnectionSettings(
            client_id="cid",
            client_secret="sec",
            redirect_uri="http://localhost:18080",
            environment="LIVE",
        )
        url = build_auth_url(s, "challenge-xyz", state="abc")
        assert "client_id=cid" in url
        assert "redirect_uri=" in url
        assert "code_challenge=challenge-xyz" in url
        assert "code_challenge_method=S256" in url
        assert "state=abc" in url
        assert "response_type=code" in url
        assert "/login/authorization/dialog" in url

    def test_build_auth_url_no_state(self):
        s = UpstoxConnectionSettings(
            client_id="cid",
            client_secret="sec",
            environment="LIVE",
        )
        url = build_auth_url(s, "ch")
        assert "state=" not in url

    def test_main_minimal(self, monkeypatch):
        from brokers.adapters.upstox.auth import login as login_mod

        s = UpstoxConnectionSettings(
            client_id="cid",
            client_secret="sec",
            redirect_uri="http://localhost:18080",
            access_token="x",
            environment="LIVE",
        )
        monkeypatch.setattr(login_mod, "UpstoxSettingsLoader", MagicMock())
        login_mod.UpstoxSettingsLoader.from_env.return_value = s

        fake_response = {"access_token": "new", "refresh_token": "new-rt"}
        monkeypatch.setattr(login_mod, "perform_login", lambda *a, **k: fake_response)

        with patch("builtins.print") as fake_print:
            rc = login_mod.main(["--no-browser", "--timeout", "0.01"])
        assert rc == 0
        fake_print.assert_called()
