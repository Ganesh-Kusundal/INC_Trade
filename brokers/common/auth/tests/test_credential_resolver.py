"""Tests for credential resolver and validator."""

from __future__ import annotations

from pathlib import Path

from brokers.common.auth.credential_resolver import CredentialResolver
from brokers.common.auth.credential_validator import CredentialValidator


class TestCredentialResolver:
    def test_resolve_dhan_default(self):
        path = CredentialResolver.resolve_env_path("dhan")
        assert path == Path(".env.local")

    def test_resolve_upstox_default(self):
        path = CredentialResolver.resolve_env_path("upstox")
        assert path in (Path(".env.upstox"), Path(".env.local"))

    def test_resolve_upstox_prefers_dedicated_file(self, tmp_path, monkeypatch):
        upstox = tmp_path / ".env.upstox"
        local = tmp_path / ".env.local"
        upstox.write_text("UPSTOX_API_KEY=k\n")
        local.write_text("UPSTOX_API_KEY=other\n")
        monkeypatch.chdir(tmp_path)
        assert CredentialResolver.resolve_upstox_env_path().resolve() == upstox.resolve()

    def test_resolve_upstox_falls_back_to_local(self, tmp_path, monkeypatch):
        local = tmp_path / ".env.local"
        local.write_text("UPSTOX_API_KEY=k\n")
        monkeypatch.chdir(tmp_path)
        assert CredentialResolver.resolve_upstox_env_path().resolve() == local.resolve()

    def test_resolve_explicit_override(self, tmp_path):
        custom = tmp_path / "custom.env"
        assert CredentialResolver.resolve_env_path("dhan", custom) == custom


class TestCredentialValidator:
    def test_paper_always_ok(self):
        ok, issues = CredentialValidator.validate_broker("paper")
        assert ok
        assert issues == []

    def test_dhan_missing_client_id(self, monkeypatch, tmp_path):
        env = tmp_path / ".env.local"
        env.write_text("DHAN_ACCESS_TOKEN=abc\n")
        monkeypatch.chdir(tmp_path)
        ok, issues = CredentialValidator.validate_broker("dhan", env)
        assert not ok
        assert any(i.field == "DHAN_CLIENT_ID" for i in issues)

    def test_dhan_ok_with_token(self, monkeypatch, tmp_path):
        env = tmp_path / ".env.local"
        env.write_text("DHAN_CLIENT_ID=cid\nDHAN_ACCESS_TOKEN=tok\n")
        monkeypatch.chdir(tmp_path)
        ok, issues = CredentialValidator.validate_broker("dhan", env)
        assert ok
        assert not any(i.severity == "error" for i in issues)
