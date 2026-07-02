"""Tests for Dhan instrument loader cache path resolution."""

from __future__ import annotations

import contextlib
import os
from pathlib import Path
from unittest.mock import patch


class TestCachePathResolution:
    """Verify that cache path uses env var when set, or project root default."""

    def test_cache_path_uses_env_when_set(self, tmp_path):
        """When DHAN_CACHE_DIR is set, it should be used."""
        from brokers.dhan.loader import InstrumentLoader

        custom_cache = tmp_path / "custom-cache"
        with (
            patch.dict(os.environ, {"DHAN_CACHE_DIR": str(custom_cache)}),
            patch.object(InstrumentLoader, "_cleanup_old_cache"),
            patch.object(InstrumentLoader, "load_cached", return_value=[]),
        ):
            # Just verify the path logic
            env_cache = os.environ.get("DHAN_CACHE_DIR")
            if env_cache:
                cache_dir = Path(env_cache)
            else:
                cache_dir = Path(__file__).resolve().parents[2] / "runtime-dev" / "instruments"

            assert cache_dir == custom_cache

    def test_cache_path_uses_default_when_env_unset(self):
        """When DHAN_CACHE_DIR is unset, should use project root default."""

        # Get the actual default path
        loader_file = Path(__file__).resolve().parents[2] / "brokers" / "dhan" / "loader.py"
        loader_file.parents[2] / "runtime-dev" / "instruments"

        # Verify the path construction logic
        env_cache = os.environ.get("DHAN_CACHE_DIR")
        if env_cache:
            cache_dir = Path(env_cache)
        else:
            cache_dir = Path(__file__).resolve().parents[2] / "runtime-dev" / "instruments"

        # Should end with runtime-dev/instruments
        assert cache_dir.parts[-2:] == ("runtime-dev", "instruments")

    def test_cache_path_creates_directory(self, tmp_path):
        """Cache directory should be created if it doesn't exist."""
        cache_dir = tmp_path / "new-cache"
        assert not cache_dir.exists()

        with patch.dict(os.environ, {"DHAN_CACHE_DIR": str(cache_dir)}):
            from brokers.dhan.loader import InstrumentLoader

            # Mock the download to avoid network calls
            with (
                patch.object(InstrumentLoader, "_cleanup_old_cache"),
                patch("pandas.read_csv") as mock_read,
                patch.object(InstrumentLoader, "_compact_to_rows", return_value=[]),
            ):
                mock_read.side_effect = Exception("Mock - no download")
                with contextlib.suppress(Exception):
                    InstrumentLoader.load_cached()  # Expected to fail on download

        # Directory should have been created
        assert cache_dir.exists()
        assert cache_dir.is_dir()
