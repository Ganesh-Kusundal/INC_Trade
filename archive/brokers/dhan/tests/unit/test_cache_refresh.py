"""Unit tests for InstrumentLoader cache, TTL, cleanup, and fallback mechanisms."""

import os
import time
import unittest.mock as mock
from datetime import date, timedelta

import pandas as pd
import pytest

from brokers.dhan.loader import InstrumentLoader


@pytest.fixture
def temp_cache_dir(tmp_path):
    """Provides a temporary cache directory and cleans it up."""
    # Use tmp_path fixture from pytest which is uniquely created per test run
    cache_dir = tmp_path / "instruments_cache"
    cache_dir.mkdir()

    # Store old env var value if any
    old_val = os.environ.get("DHAN_CACHE_DIR")
    os.environ["DHAN_CACHE_DIR"] = str(cache_dir)

    yield cache_dir

    # Restore old env var value
    if old_val is not None:
        os.environ["DHAN_CACHE_DIR"] = old_val
    else:
        os.environ.pop("DHAN_CACHE_DIR", None)


def test_configurable_cache_dir(temp_cache_dir):
    """Verify that cache directory path is configured via DHAN_CACHE_DIR."""
    assert os.environ["DHAN_CACHE_DIR"] == str(temp_cache_dir)

    # Mock network call to pd.read_csv to return a minimal DataFrame
    mock_df = pd.DataFrame(
        [
            {
                "SEM_TRADING_SYMBOL": "RELIANCE",
                "SEM_SMST_SECURITY_ID": 2885,
                "SEM_EXM_EXCH_ID": "NSE",
                "SEM_SEGMENT": "E",
                "SEM_INSTRUMENT_NAME": "EQUITY",
            }
        ]
    )

    with (
        mock.patch("pandas.read_csv", return_value=mock_df),
        mock.patch("brokers.dhan.loader.InstrumentLoader._fetch_mcx_detailed", return_value=[]),
    ):
        rows = InstrumentLoader.load_cached(force_refresh=True)

    today = date.today().isoformat()
    expected_file = temp_cache_dir / f"instruments_{today}.csv"
    assert expected_file.exists()
    assert expected_file.stat().st_size > 0
    assert len(rows) == 1
    assert rows[0]["SEM_TRADING_SYMBOL"] == "RELIANCE"


def test_cache_ttl_less_than_6_hours(temp_cache_dir):
    """Verify that cache is NOT refreshed if it's less than 6 hours old."""
    # Create a dummy cache file for today
    today = date.today().isoformat()
    cache_path = temp_cache_dir / f"instruments_{today}.csv"

    mock_df = pd.DataFrame(
        [
            {
                "SEM_TRADING_SYMBOL": "CACHED_VAL",
                "SEM_SMST_SECURITY_ID": 123,
                "SEM_EXM_EXCH_ID": "NSE",
                "SEM_SEGMENT": "E",
                "SEM_INSTRUMENT_NAME": "EQUITY",
            }
        ]
    )
    mock_df.to_csv(cache_path, index=False)

    # Set mtime to 3 hours ago
    three_hours_ago = time.time() - (3 * 3600)
    os.utime(cache_path, (three_hours_ago, three_hours_ago))

    with (
        mock.patch("pandas.read_csv") as mock_read_csv,
        mock.patch("brokers.dhan.loader.InstrumentLoader._fetch_mcx_detailed", return_value=[]),
    ):
        # When reading cache, pd.read_csv is called with cache_path.
        # We configure it to return the mock_df.
        mock_read_csv.return_value = mock_df

        rows = InstrumentLoader.load_cached(force_refresh=False)

        # Verify that we read from the cache file
        mock_read_csv.assert_called_once()
        assert str(mock_read_csv.call_args[0][0]) == str(cache_path)

    assert len(rows) == 1
    assert rows[0]["SEM_TRADING_SYMBOL"] == "CACHED_VAL"


def test_cache_ttl_more_than_6_hours_forces_refresh(temp_cache_dir):
    """Verify that cache IS refreshed if it's more than 6 hours old."""
    today = date.today().isoformat()
    cache_path = temp_cache_dir / f"instruments_{today}.csv"

    # Create stale cache
    old_df = pd.DataFrame(
        [
            {
                "SEM_TRADING_SYMBOL": "STALE_VAL",
                "SEM_SMST_SECURITY_ID": 123,
                "SEM_EXM_EXCH_ID": "NSE",
                "SEM_SEGMENT": "E",
                "SEM_INSTRUMENT_NAME": "EQUITY",
            }
        ]
    )
    old_df.to_csv(cache_path, index=False)

    # Set mtime to 7 hours ago
    seven_hours_ago = time.time() - (7 * 3600)
    os.utime(cache_path, (seven_hours_ago, seven_hours_ago))

    # Fresh data from server
    fresh_df = pd.DataFrame(
        [
            {
                "SEM_TRADING_SYMBOL": "FRESH_VAL",
                "SEM_SMST_SECURITY_ID": 456,
                "SEM_EXM_EXCH_ID": "NSE",
                "SEM_SEGMENT": "E",
                "SEM_INSTRUMENT_NAME": "EQUITY",
            }
        ]
    )

    # We patch read_csv. When it loads from URL (fresh download), it returns fresh_df.
    with (
        mock.patch("pandas.read_csv", return_value=fresh_df) as mock_read_csv,
        mock.patch("brokers.dhan.loader.InstrumentLoader._fetch_mcx_detailed", return_value=[]),
    ):
        rows = InstrumentLoader.load_cached(force_refresh=False)

        # Verify it downloaded fresh from URL (read_csv called on _COMPACT_CSV_URL)
        assert mock_read_csv.call_count >= 1
        called_urls = [str(call[0][0]) for call in mock_read_csv.call_args_list]
        assert any("images.dhan.co" in url for url in called_urls)

    assert len(rows) == 1
    assert rows[0]["SEM_TRADING_SYMBOL"] == "FRESH_VAL"


def test_graceful_fallback_on_download_failure(temp_cache_dir):
    """Verify that loader falls back to stale cache if server is offline/download fails."""
    today = date.today().isoformat()
    cache_path = temp_cache_dir / f"instruments_{today}.csv"

    cached_df = pd.DataFrame(
        [
            {
                "SEM_TRADING_SYMBOL": "STALE_FALLBACK_VAL",
                "SEM_SMST_SECURITY_ID": 789,
                "SEM_EXM_EXCH_ID": "NSE",
                "SEM_SEGMENT": "E",
                "SEM_INSTRUMENT_NAME": "EQUITY",
            }
        ]
    )
    cached_df.to_csv(cache_path, index=False)

    # Set mtime to 7 hours ago to trigger refresh attempt
    seven_hours_ago = time.time() - (7 * 3600)
    os.utime(cache_path, (seven_hours_ago, seven_hours_ago))

    # Mock read_csv to fail on URL download but succeed on local file read
    def side_effect(path, *args, **kwargs):
        if "images.dhan.co" in str(path):
            raise ConnectionError("Server offline")
        return cached_df

    with (
        mock.patch("pandas.read_csv", side_effect=side_effect),
        mock.patch("brokers.dhan.loader.InstrumentLoader._fetch_mcx_detailed", return_value=[]),
    ):
        rows = InstrumentLoader.load_cached(force_refresh=False)

    # Should fall back to stale cache value instead of raising exception
    assert len(rows) == 1
    assert rows[0]["SEM_TRADING_SYMBOL"] == "STALE_FALLBACK_VAL"


def test_cache_cleanup_older_than_7_days(temp_cache_dir):
    """Verify that cache files older than 7 days are automatically deleted."""
    t_today = date.today()
    files_to_create = [
        (t_today.isoformat(), 0),
        ((t_today - timedelta(days=5)).isoformat(), 5),
        ((t_today - timedelta(days=8)).isoformat(), 8),
        ((t_today - timedelta(days=10)).isoformat(), 10),
    ]

    created_paths = []
    dummy_df = pd.DataFrame(
        [
            {
                "SEM_TRADING_SYMBOL": "TEST",
                "SEM_SMST_SECURITY_ID": 1,
                "SEM_EXM_EXCH_ID": "NSE",
                "SEM_SEGMENT": "E",
                "SEM_INSTRUMENT_NAME": "EQUITY",
            }
        ]
    )

    for suffix, age_days in files_to_create:
        p = temp_cache_dir / f"instruments_{suffix}.csv"
        dummy_df.to_csv(p, index=False)
        # Set mtime back in time
        file_age_seconds = age_days * 24 * 3600 + 3600  # add 1 hour buffer
        mtime = time.time() - file_age_seconds
        os.utime(p, (mtime, mtime))
        created_paths.append((p, age_days))

    # Run cache load (which triggers cleanup)
    with (
        mock.patch("pandas.read_csv", return_value=dummy_df),
        mock.patch("brokers.dhan.loader.InstrumentLoader._fetch_mcx_detailed", return_value=[]),
    ):
        InstrumentLoader.load_cached(force_refresh=False)

    # Verify file existence
    for p, age_days in created_paths:
        if age_days >= 8:
            assert not p.exists(), f"File older than 7 days should have been deleted: {p}"
        else:
            assert p.exists(), f"File newer than 7 days should not have been deleted: {p}"
