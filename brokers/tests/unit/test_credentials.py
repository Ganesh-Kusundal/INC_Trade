"""Tests for credential resolution."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


from inc_trade.infrastructure.credentials import (
    CANONICAL_ENV_FILES,
    CredentialResolver,
    read_secret,
)


class TestCredentialResolver:
    def setup_method(self):
        self._tmpdir = tempfile.mkdtemp()
        self.resolver = CredentialResolver(project_root=Path(self._tmpdir))

    def test_resolve_dhan_env_path(self):
        path = self.resolver.resolve_env_path("dhan")
        assert path is not None
        assert path.name == ".env.local"

    def test_resolve_upstox_env_path(self):
        path = self.resolver.resolve_env_path("upstox")
        assert path is not None
        assert path.name == ".env.upstox"

    def test_resolve_paper_returns_none(self):
        assert self.resolver.resolve_env_path("paper") is None

    def test_load_broker_env_sets_variables(self):
        env_file = Path(self._tmpdir) / ".env.local"
        env_file.write_text("DHAN_TEST_KEY=test_value_123\n# comment\n")

        key = "DHAN_TEST_KEY"
        os.environ.pop(key, None)
        try:
            result = self.resolver.load_broker_env("dhan")
            assert result is True
            assert os.environ.get(key) == "test_value_123"
        finally:
            os.environ.pop(key, None)

    def test_load_broker_env_does_not_overwrite(self):
        env_file = Path(self._tmpdir) / ".env.local"
        env_file.write_text("DHAN_EXISTING=from_file\n")

        key = "DHAN_EXISTING"
        os.environ[key] = "from_env"
        try:
            self.resolver.load_broker_env("dhan")
            assert os.environ[key] == "from_env"
        finally:
            os.environ.pop(key, None)

    def test_load_missing_file_returns_false(self):
        assert self.resolver.load_broker_env("dhan") is False


class TestReadSecret:
    def test_reads_from_env(self):
        os.environ["TEST_SECRET_KEY"] = "env_value"
        try:
            assert read_secret("TEST_SECRET_KEY") == "env_value"
        finally:
            os.environ.pop("TEST_SECRET_KEY", None)

    def test_reads_from_file_fallback(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("file_secret_value")
            f.flush()
            try:
                os.environ.pop("TEST_FILE_SECRET", None)
                os.environ["TEST_FILE_PATH"] = f.name
                result = read_secret("TEST_FILE_SECRET", file_key="TEST_FILE_PATH")
                assert result == "file_secret_value"
            finally:
                os.environ.pop("TEST_FILE_SECRET", None)
                os.environ.pop("TEST_FILE_PATH", None)
                Path(f.name).unlink(missing_ok=True)

    def test_returns_empty_when_missing(self):
        os.environ.pop("NONEXISTENT_KEY", None)
        assert read_secret("NONEXISTENT_KEY") == ""


class TestCanonicalEnvFiles:
    def test_dhan_maps_to_env_local(self):
        assert CANONICAL_ENV_FILES["dhan"] == ".env.local"

    def test_upstox_maps_to_env_upstox(self):
        assert CANONICAL_ENV_FILES["upstox"] == ".env.upstox"

    def test_paper_is_none(self):
        assert CANONICAL_ENV_FILES["paper"] is None
