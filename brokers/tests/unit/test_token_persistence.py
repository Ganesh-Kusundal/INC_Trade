"""Tests for token persistence infrastructure."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from inc_trade.infrastructure.storage.token_store import (
    JsonTokenStateStore,
    TokenSource,
    TokenState,
    compute_token_expiry,
    update_env_token,
)


class TestTokenState:
    def test_is_valid_with_token(self):
        state = TokenState(access_token="test-token")
        assert state.is_valid()

    def test_is_valid_empty_token(self):
        state = TokenState(access_token="")
        assert not state.is_valid()

    def test_is_valid_expired(self):
        state = TokenState(
            access_token="test-token",
            expires_at=datetime.now() - timedelta(hours=1),
        )
        assert not state.is_valid()

    def test_is_valid_not_expired(self):
        state = TokenState(
            access_token="test-token",
            expires_at=datetime.now() + timedelta(hours=1),
        )
        assert state.is_valid()

    def test_remaining_seconds_no_expiry(self):
        state = TokenState(access_token="test-token")
        assert state.remaining_seconds() == float("inf")

    def test_remaining_seconds_expired(self):
        state = TokenState(
            access_token="test-token",
            expires_at=datetime.now() - timedelta(hours=1),
        )
        assert state.remaining_seconds() < 0

    def test_refresh_recommended_no_expiry(self):
        state = TokenState(access_token="test-token")
        assert not state.refresh_recommended()

    def test_refresh_recommended_within_buffer(self):
        state = TokenState(
            access_token="test-token",
            expires_at=datetime.now() + timedelta(minutes=2),
        )
        assert state.refresh_recommended(buffer_seconds=300.0)

    def test_refresh_recommended_outside_buffer(self):
        state = TokenState(
            access_token="test-token",
            expires_at=datetime.now() + timedelta(hours=2),
        )
        assert not state.refresh_recommended(buffer_seconds=300.0)


class TestJsonTokenStateStore:
    def test_save_and_load(self, tmp_path):
        store = JsonTokenStateStore(tmp_path / "token.json")
        state = TokenState(
            access_token="test-token",
            source=TokenSource.TOTP,
            issued_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        store.save(state)
        loaded = store.load()
        assert loaded is not None
        assert loaded.access_token == "test-token"
        assert loaded.source == TokenSource.TOTP

    def test_load_missing_file(self, tmp_path):
        store = JsonTokenStateStore(tmp_path / "nonexistent.json")
        assert store.load() is None

    def test_save_none_deletes_file(self, tmp_path):
        store = JsonTokenStateStore(tmp_path / "token.json")
        state = TokenState(access_token="test-token")
        store.save(state)
        assert (tmp_path / "token.json").exists()
        store.save(None)
        assert not (tmp_path / "token.json").exists()

    def test_load_corrupt_file(self, tmp_path):
        path = tmp_path / "token.json"
        path.write_text("not valid json")
        store = JsonTokenStateStore(path)
        assert store.load() is None

    def test_file_permissions(self, tmp_path):
        store = JsonTokenStateStore(tmp_path / "token.json")
        state = TokenState(access_token="test-token")
        store.save(state)
        mode = (tmp_path / "token.json").stat().st_mode & 0o777
        assert mode == 0o600


class TestUpdateEnvToken:
    def test_update_existing_key(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("DHAN_ACCESS_TOKEN=old-token\nOTHER=value\n")
        update_env_token(env_file, "new-token")
        content = env_file.read_text()
        assert "DHAN_ACCESS_TOKEN=new-token" in content
        assert "OTHER=value" in content

    def test_add_new_key(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("OTHER=value\n")
        update_env_token(env_file, "new-token")
        content = env_file.read_text()
        assert "DHAN_ACCESS_TOKEN=new-token" in content

    def test_custom_key(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("UPSTOX_TOKEN=old\n")
        update_env_token(env_file, "new-token", env_key="UPSTOX_TOKEN")
        content = env_file.read_text()
        assert "UPSTOX_TOKEN=new-token" in content

    def test_missing_file(self, tmp_path):
        env_file = tmp_path / ".env"
        update_env_token(env_file, "new-token")
        assert not env_file.exists()


class TestComputeTokenExpiry:
    def test_returns_future_datetime(self):
        expiry = compute_token_expiry()
        assert expiry > datetime.now(UTC)

    def test_returns_datetime_object(self):
        expiry = compute_token_expiry()
        assert isinstance(expiry, datetime)
