"""Tests for brokers.common.auth — token management, TOTP, credentials.

Covers:
  - TokenState: validity, expiry, serialization
  - TotpGenerator: RFC 6238 TOTP code generation
  - TotpCooldownGuard: cooldown enforcement
  - AuthManager: acquire, ensure_valid, ensure_fresh, refresh, receivers
  - JsonTokenStateStore: save/load/clear
  - EnvTokenStateStore: load from env
  - CredentialResolver: for_dhan, for_upstox
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from brokers.common.auth.token_manager import (
    AuthManager,
    EnvTokenStateStore,
    JsonTokenStateStore,
    TokenSource,
    TokenState,
    TotpCooldownGuard,
    TotpGenerator,
)
from brokers.common.auth.credential_resolver import (
    CredentialResolver,
)


# ── TokenState tests ───────────────────────────────────────────────────────


class TestTokenState:
    def test_is_valid_no_expiry(self):
        state = TokenState(access_token="tok123")
        assert state.is_valid is True

    def test_is_valid_future_expiry(self):
        expiry = datetime.now(timezone.utc) + timedelta(hours=1)
        state = TokenState(access_token="tok", expires_at=expiry)
        assert state.is_valid is True

    def test_is_invalid_past_expiry(self):
        expiry = datetime.now(timezone.utc) - timedelta(hours=1)
        state = TokenState(access_token="tok", expires_at=expiry)
        assert state.is_valid is False

    def test_remaining_seconds(self):
        expiry = datetime.now(timezone.utc) + timedelta(seconds=100)
        state = TokenState(access_token="tok", expires_at=expiry)
        assert 90 < state.remaining_seconds <= 100

    def test_remaining_seconds_no_expiry(self):
        state = TokenState(access_token="tok")
        assert state.remaining_seconds == float("inf")

    def test_refresh_recommended_within_buffer(self):
        expiry = datetime.now(timezone.utc) + timedelta(seconds=60)
        state = TokenState(access_token="tok", expires_at=expiry)
        assert state.refresh_recommended(buffer_seconds=300) is True

    def test_refresh_not_recommended(self):
        expiry = datetime.now(timezone.utc) + timedelta(hours=2)
        state = TokenState(access_token="tok", expires_at=expiry)
        assert state.refresh_recommended(buffer_seconds=300) is False

    def test_from_expiry_seconds(self):
        state = TokenState.from_expiry_seconds("tok", 300, source=TokenSource.TOTP, broker_id="dhan")
        assert state.access_token == "tok"
        assert state.source == TokenSource.TOTP
        assert state.is_valid is True
        assert 290 < state.remaining_seconds <= 300

    def test_serialization_roundtrip(self):
        expiry = datetime.now(timezone.utc) + timedelta(hours=1)
        original = TokenState(
            access_token="tok",
            refresh_token="ref",
            expires_at=expiry,
            source=TokenSource.TOTP,
            broker_id="dhan",
        )
        data = original.to_dict()
        restored = TokenState.from_dict(data)
        assert restored.access_token == "tok"
        assert restored.refresh_token == "ref"
        assert restored.source == TokenSource.TOTP
        assert restored.broker_id == "dhan"

    def test_immutable(self):
        state = TokenState(access_token="tok")
        with pytest.raises(AttributeError):
            state.access_token = "other"  # type: ignore


# ── TotpGenerator tests ────────────────────────────────────────────────────


class TestTotpGenerator:
    # Test vector from RFC 6238 Appendix B
    # Secret: "12345678901234567890" (ASCII) → base32: GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ
    RFC_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"

    def test_generates_6_digit_code(self):
        code = TotpGenerator.code_now(self.RFC_SECRET)
        assert len(code) == 6
        assert code.isdigit()

    def test_same_timestamp_same_code(self):
        ts = 1234567890.0
        code1 = TotpGenerator.code_at(self.RFC_SECRET, ts)
        code2 = TotpGenerator.code_at(self.RFC_SECRET, ts)
        assert code1 == code2

    def test_different_timestamp_different_code(self):
        code1 = TotpGenerator.code_at(self.RFC_SECRET, 1000000.0)
        code2 = TotpGenerator.code_at(self.RFC_SECRET, 1000031.0)  # +31s → next window
        assert code1 != code2

    def test_handles_spaces_in_secret(self):
        # Shorter secret that works with both spaced and compact forms
        secret = "JBSWY3DPEHPK3PXP"
        secret_with_spaces = "JBSW Y3DP EHPK 3PXP"
        code1 = TotpGenerator.code_now(secret_with_spaces)
        code2 = TotpGenerator.code_now(secret)
        assert code1 == code2

    def test_handles_dashes_in_secret(self):
        secret = "JBSWY3DPEHPK3PXP"
        secret_with_dashes = "JBSW-Y3DP-EHPK-3PXP"
        code1 = TotpGenerator.code_now(secret_with_dashes)
        code2 = TotpGenerator.code_now(secret)
        assert code1 == code2

    def test_seconds_remaining(self):
        remaining = TotpGenerator.seconds_remaining(1000000.0)
        # 1000000 % 30 = 10, so 30-10=20
        assert remaining == 20


# ── TotpCooldownGuard tests ────────────────────────────────────────────────


class TestTotpCooldownGuard:
    def test_can_generate_initially(self):
        guard = TotpCooldownGuard(cooldown_seconds=60)
        assert guard.can_generate() is True

    def test_cannot_generate_after_attempt(self):
        guard = TotpCooldownGuard(cooldown_seconds=60)
        guard.record_attempt()
        assert guard.can_generate() is False

    def test_seconds_until_allowed(self):
        guard = TotpCooldownGuard(cooldown_seconds=60)
        guard.record_attempt()
        remaining = guard.seconds_until_allowed()
        assert 55 <= remaining <= 60

    def test_can_generate_after_cooldown(self):
        guard = TotpCooldownGuard(cooldown_seconds=0)
        guard.record_attempt()
        # With 0 cooldown, should be allowed immediately
        time.sleep(0.01)
        assert guard.can_generate() is True

    def test_reset_clears_cooldown(self):
        guard = TotpCooldownGuard(cooldown_seconds=60)
        guard.record_attempt()
        assert guard.can_generate() is False
        guard.reset()
        assert guard.can_generate() is True

    def test_persist_to_file(self, tmp_path: Path):
        persist = tmp_path / "cooldown.json"
        guard = TotpCooldownGuard(cooldown_seconds=60, persist_path=persist)
        guard.record_attempt()
        assert persist.exists()

        # New guard should load persisted state
        guard2 = TotpCooldownGuard(cooldown_seconds=60, persist_path=persist)
        assert guard2.can_generate() is False


# ── AuthManager tests ──────────────────────────────────────────────────────


class TestAuthManager:
    def test_acquire_calls_callback(self):
        calls = []
        def acquire_fn() -> TokenState:
            calls.append(1)
            return TokenState(access_token="fresh_token", source=TokenSource.TOTP)

        manager = AuthManager(on_acquire=acquire_fn, broker_name="test")
        state = manager.acquire()
        assert state.access_token == "fresh_token"
        assert len(calls) == 1
        assert manager.refresh_count == 1

    def test_ensure_valid_with_valid_token(self):
        def acquire_fn() -> TokenState:
            return TokenState(access_token="tok")

        manager = AuthManager(on_acquire=acquire_fn, broker_name="test")
        manager.acquire()  # Get initial token
        # Second call should NOT re-acquire
        state = manager.ensure_valid()
        assert state.access_token == "tok"
        assert manager.refresh_count == 1  # Still 1

    def test_ensure_valid_with_expired_token(self):
        call_count = [0]
        def acquire_fn() -> TokenState:
            call_count[0] += 1
            if call_count[0] == 1:
                return TokenState(
                    access_token="old",
                    expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
                )
            return TokenState(access_token="new")

        manager = AuthManager(on_acquire=acquire_fn, broker_name="test")
        manager.acquire()
        state = manager.ensure_valid()
        assert state.access_token == "new"
        assert call_count[0] == 2

    def test_refresh_calls_on_refresh(self):
        def acquire_fn() -> TokenState:
            return TokenState(access_token="initial")

        def refresh_fn(old: TokenState) -> TokenState:
            return TokenState(access_token="refreshed", source=TokenSource.REFRESH)

        manager = AuthManager(on_acquire=acquire_fn, on_refresh=refresh_fn, broker_name="test")
        manager.acquire()
        state = manager.refresh()
        assert state.access_token == "refreshed"
        assert state.source == TokenSource.REFRESH

    def test_refresh_without_callback_falls_back_to_acquire(self):
        def acquire_fn() -> TokenState:
            return TokenState(access_token="fresh")

        manager = AuthManager(on_acquire=acquire_fn, broker_name="test")
        manager.acquire()
        state = manager.refresh()
        assert state.access_token == "fresh"

    def test_token_receiver_called_on_acquire(self):
        received: list[str] = []

        def acquire_fn() -> TokenState:
            return TokenState(access_token="tok1")

        manager = AuthManager(on_acquire=acquire_fn, broker_name="test")
        manager.register_token_receiver(lambda t: received.append(t))
        manager.acquire()
        assert received == ["tok1"]

    def test_token_receiver_called_on_refresh(self):
        received: list[str] = []

        def acquire_fn() -> TokenState:
            return TokenState(access_token="tok1")

        def refresh_fn(old: TokenState) -> TokenState:
            return TokenState(access_token="tok2")

        manager = AuthManager(
            on_acquire=acquire_fn, on_refresh=refresh_fn, broker_name="test",
        )
        manager.register_token_receiver(lambda t: received.append(t))
        manager.acquire()
        manager.refresh()
        assert received == ["tok1", "tok2"]

    def test_unregister_token_receiver(self):
        received: list[str] = []
        def cb(t):
            return received.append(t)

        manager = AuthManager(on_acquire=lambda: TokenState(access_token="tok"), broker_name="test")
        manager.register_token_receiver(cb)
        manager.unregister_token_receiver(cb)
        manager.acquire()
        assert received == []

    def test_revoke_clears_state(self):
        manager = AuthManager(
            on_acquire=lambda: TokenState(access_token="tok"),
            broker_name="test",
        )
        manager.acquire()
        assert manager.is_valid is True
        manager.revoke()
        assert manager.is_valid is False

    def test_access_token_raises_when_no_token(self):
        manager = AuthManager(broker_name="test")
        with pytest.raises(RuntimeError):
            _ = manager.access_token

    def test_error_count_on_acquire_failure(self):
        def fail_acquire() -> TokenState:
            raise ValueError("login failed")

        manager = AuthManager(on_acquire=fail_acquire, broker_name="test")
        with pytest.raises(ValueError):
            manager.acquire()
        assert manager.error_count == 1


# ── JsonTokenStateStore tests ──────────────────────────────────────────────


class TestJsonTokenStateStore:
    def test_save_and_load(self, tmp_path: Path):
        path = tmp_path / "token.json"
        store = JsonTokenStateStore(path)
        state = TokenState(
            access_token="tok123",
            refresh_token="ref456",
            source=TokenSource.TOTP,
            broker_id="dhan",
        )
        store.save(state)
        loaded = store.load()
        assert loaded is not None
        assert loaded.access_token == "tok123"
        assert loaded.refresh_token == "ref456"
        assert loaded.source == TokenSource.TOTP

    def test_load_returns_none_when_not_found(self, tmp_path: Path):
        store = JsonTokenStateStore(tmp_path / "nonexistent.json")
        assert store.load() is None

    def test_clear_removes_file(self, tmp_path: Path):
        path = tmp_path / "token.json"
        store = JsonTokenStateStore(path)
        store.save(TokenState(access_token="tok"))
        assert path.exists()
        store.clear()
        assert not path.exists()

    def test_load_corrupt_file_returns_none(self, tmp_path: Path):
        path = tmp_path / "token.json"
        path.write_text("{invalid json}")
        store = JsonTokenStateStore(path)
        assert store.load() is None


# ── EnvTokenStateStore tests ───────────────────────────────────────────────


class TestEnvTokenStateStore:
    def test_load_from_env(self):
        with patch.dict(os.environ, {
            "TEST_ACCESS_TOKEN": "env_tok",
            "TEST_CLIENT_ID": "client123",
        }):
            store = EnvTokenStateStore(prefix="TEST")
            state = store.load()
            assert state is not None
            assert state.access_token == "env_tok"
            assert state.broker_id == "client123"

    def test_load_returns_none_when_no_token(self):
        # Ensure env vars are not set
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("NONEXIST_ACCESS_TOKEN", None)
            store = EnvTokenStateStore(prefix="NONEXIST")
            assert store.load() is None


# ── CredentialResolver tests ───────────────────────────────────────────────


class TestCredentialResolver:
    def test_for_dhan_from_env(self):
        # Use a non-existent env_file to avoid loading .env.local from project root
        # and clear all DHAN_ vars to ensure clean state
        dhan_backup = {k: os.environ.pop(k) for k in list(os.environ) if k.startswith("DHAN_")}
        try:
            os.environ["DHAN_CLIENT_ID"] = "dhan123"
            os.environ["DHAN_ACCESS_TOKEN"] = "tok_dhan"
            creds = CredentialResolver.for_dhan(env_file="/nonexistent/path/.env.dhan")
            assert creds.client_id == "dhan123"
            assert creds.access_token == "tok_dhan"
            assert creds.has_totp is False
        finally:
            # Restore original env
            for k in list(os.environ):
                if k.startswith("DHAN_"):
                    del os.environ[k]
            os.environ.update(dhan_backup)

    def test_for_dhan_with_totp(self):
        with patch.dict(os.environ, {
            "DHAN_CLIENT_ID": "dhan123",
            "DHAN_TOTP_SECRET": "JBSWY3DPEHPK3PXP",
            "DHAN_PIN": "1234",
        }, clear=False):
            os.environ.pop("DHAN_ACCESS_TOKEN", None)
            creds = CredentialResolver.for_dhan()
            assert creds.has_totp is True
            assert creds.totp_secret == "JBSWY3DPEHPK3PXP"

    def test_for_dhan_missing_client_id_raises(self):
        # Remove ALL DHAN_ env vars and use non-existent env_file
        dhan_backup = {k: os.environ.pop(k) for k in list(os.environ) if k.startswith("DHAN_")}
        try:
            with pytest.raises(ValueError, match="DHAN_CLIENT_ID"):
                CredentialResolver.for_dhan(env_file="/nonexistent/path/.env.dhan")
        finally:
            os.environ.update(dhan_backup)

    def test_for_upstox_from_env(self):
        with patch.dict(os.environ, {
            "UPSTOX_CLIENT_ID": "upstox123",
            "UPSTOX_ACCESS_TOKEN": "tok_up",
        }):
            creds = CredentialResolver.for_upstox()
            assert creds.client_id == "upstox123"
            assert creds.access_token == "tok_up"

    def test_for_upstox_with_totp(self):
        with patch.dict(os.environ, {
            "UPSTOX_CLIENT_ID": "up123",
            "UPSTOX_MOBILE": "+919876543210",
            "UPSTOX_PIN": "1234",
            "UPSTOX_TOTP_SECRET": "JBSWY3DPEHPK3PXP",
        }, clear=False):
            os.environ.pop("UPSTOX_ACCESS_TOKEN", None)
            os.environ.pop("UPSTOX_API_KEY", None)
            creds = CredentialResolver.for_upstox()
            assert creds.has_totp is True

    def test_for_dhan_from_env_file(self, tmp_path: Path):
        # Remove all DHAN_ env vars first so the env file is the sole source
        env_backup = {}
        for k in list(os.environ.keys()):
            if k.startswith("DHAN_"):
                env_backup[k] = os.environ.pop(k)
        try:
            env_file = tmp_path / ".env.dhan"
            env_file.write_text(
                "DHAN_CLIENT_ID=file_client\nDHAN_ACCESS_TOKEN=file_tok\n"
            )
            creds = CredentialResolver.for_dhan(env_file=env_file)
            assert creds.client_id == "file_client"
            assert creds.access_token == "file_tok"
        finally:
            os.environ.update(env_backup)
