"""Unit tests for Dhan InstrumentLoader disk cache and MCX supplement."""

from __future__ import annotations

import os
import time
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from brokers.adapters.dhan.identity import DhanInstrumentResolver
from brokers.adapters.dhan.instrument_loader import InstrumentLoader

_FIXTURES = Path(__file__).parent / "fixtures"
_COMPACT_FIXTURE = _FIXTURES / "compact_instruments.csv"
_MCX_FIXTURE = _FIXTURES / "mcx_detailed.csv"


@pytest.fixture
def temp_cache_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    cache_dir = tmp_path / "instruments_cache"
    cache_dir.mkdir()
    monkeypatch.setenv("DHAN_CACHE_DIR", str(cache_dir))
    return cache_dir


def test_cache_path_uses_env_when_set(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    custom_cache = tmp_path / "custom-cache"
    monkeypatch.setenv("DHAN_CACHE_DIR", str(custom_cache))
    assert InstrumentLoader.resolve_cache_dir() == custom_cache


def test_cache_path_uses_default_when_env_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DHAN_CACHE_DIR", raising=False)
    cache_dir = InstrumentLoader.resolve_cache_dir()
    assert cache_dir.parts[-2:] == ("runtime-dev", "instruments")


def test_cache_path_creates_directory(temp_cache_dir: Path) -> None:
    compact_text = _COMPACT_FIXTURE.read_text(encoding="utf-8")

    with patch.object(
        InstrumentLoader, "_download_compact_csv", return_value=compact_text
    ):
        InstrumentLoader.load_csv_text(
            force_refresh=True,
            mcx_csv_path=_MCX_FIXTURE,
        )

    assert temp_cache_dir.exists()
    assert temp_cache_dir.is_dir()


def test_configurable_cache_dir_writes_file(temp_cache_dir: Path) -> None:
    compact_text = _COMPACT_FIXTURE.read_text(encoding="utf-8")

    with patch.object(
        InstrumentLoader, "_download_compact_csv", return_value=compact_text
    ):
        text = InstrumentLoader.load_csv_text(
            force_refresh=True,
            mcx_csv_path=_MCX_FIXTURE,
        )

    today = date.today().isoformat()
    expected_file = temp_cache_dir / f"instruments_{today}.csv"
    assert expected_file.exists()
    assert expected_file.stat().st_size > 0
    assert "RELIANCE" in text


def test_cache_ttl_less_than_6_hours(temp_cache_dir: Path) -> None:
    today = date.today().isoformat()
    cache_path = temp_cache_dir / f"instruments_{today}.csv"
    cache_path.write_text(_COMPACT_FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")

    three_hours_ago = time.time() - (3 * 3600)
    os.utime(cache_path, (three_hours_ago, three_hours_ago))

    with patch.object(InstrumentLoader, "_download_compact_csv") as mock_download:
        text = InstrumentLoader.load_csv_text(
            force_refresh=False,
            mcx_csv_path=_MCX_FIXTURE,
        )
        mock_download.assert_not_called()

    assert "RELIANCE" in text
    assert "GOLD" in text


def test_cache_ttl_more_than_6_hours_forces_refresh(temp_cache_dir: Path) -> None:
    today = date.today().isoformat()
    cache_path = temp_cache_dir / f"instruments_{today}.csv"
    cache_path.write_text("SEM_TRADING_SYMBOL,SEM_SMST_SECURITY_ID,SEM_EXM_EXCH_ID,SEM_INSTRUMENT_NAME,SEM_LOT_UNITS\nSTALE,1,NSE,EQUITY,1.0\n", encoding="utf-8")

    seven_hours_ago = time.time() - (7 * 3600)
    os.utime(cache_path, (seven_hours_ago, seven_hours_ago))

    fresh_text = _COMPACT_FIXTURE.read_text(encoding="utf-8")
    with patch.object(
        InstrumentLoader, "_download_compact_csv", return_value=fresh_text
    ) as mock_download:
        text = InstrumentLoader.load_csv_text(
            force_refresh=False,
            mcx_csv_path=_MCX_FIXTURE,
        )
        mock_download.assert_called_once()

    assert "RELIANCE" in text
    assert "STALE" not in text


def test_graceful_fallback_on_download_failure(temp_cache_dir: Path) -> None:
    today = date.today().isoformat()
    cache_path = temp_cache_dir / f"instruments_{today}.csv"
    stale_csv = (
        "SEM_TRADING_SYMBOL,SEM_SMST_SECURITY_ID,SEM_EXM_EXCH_ID,SEM_INSTRUMENT_NAME,SEM_LOT_UNITS\n"
        "STALE_FALLBACK,789,NSE,EQUITY,1.0\n"
    )
    cache_path.write_text(stale_csv, encoding="utf-8")

    seven_hours_ago = time.time() - (7 * 3600)
    os.utime(cache_path, (seven_hours_ago, seven_hours_ago))

    with (
        patch.object(
            InstrumentLoader,
            "_download_compact_csv",
            side_effect=ConnectionError("Server offline"),
        ),
        patch.object(InstrumentLoader, "_download_mcx_detailed_csv", return_value=""),
    ):
        text = InstrumentLoader.load_csv_text(force_refresh=False)

    assert "STALE_FALLBACK" in text


def test_cache_cleanup_older_than_7_days(temp_cache_dir: Path) -> None:
    t_today = date.today()
    files_to_create = [
        (t_today.isoformat(), 0),
        ((t_today - timedelta(days=5)).isoformat(), 5),
        ((t_today - timedelta(days=8)).isoformat(), 8),
        ((t_today - timedelta(days=10)).isoformat(), 10),
    ]

    stale_row = (
        "SEM_TRADING_SYMBOL,SEM_SMST_SECURITY_ID,SEM_EXM_EXCH_ID,SEM_INSTRUMENT_NAME,SEM_LOT_UNITS\n"
        "TEST,1,NSE,EQUITY,1.0\n"
    )
    created_paths: list[tuple[Path, int]] = []
    for suffix, age_days in files_to_create:
        path = temp_cache_dir / f"instruments_{suffix}.csv"
        path.write_text(stale_row, encoding="utf-8")
        mtime = time.time() - (age_days * 24 * 3600 + 3600)
        os.utime(path, (mtime, mtime))
        created_paths.append((path, age_days))

    with patch.object(
        InstrumentLoader, "_download_compact_csv", return_value=_COMPACT_FIXTURE.read_text()
    ):
        InstrumentLoader.load_csv_text(force_refresh=False, mcx_csv_path=_MCX_FIXTURE)

    for path, age_days in created_paths:
        if age_days >= 8:
            assert not path.exists(), f"Expected deletion: {path}"
        else:
            assert path.exists(), f"Expected retention: {path}"


def test_mcx_supplement_merges_from_local_fixture(temp_cache_dir: Path) -> None:
    compact_text = _COMPACT_FIXTURE.read_text(encoding="utf-8")
    with patch.object(
        InstrumentLoader, "_download_compact_csv", return_value=compact_text
    ):
        text = InstrumentLoader.load_csv_text(
            force_refresh=True,
            mcx_csv_path=_MCX_FIXTURE,
        )

    assert "GOLD-05Aug2025-FUT" in text
    assert "CRUDEOIL-19Sep2025-FUT" in text


def test_mcx_required_raises_when_supplement_missing(temp_cache_dir: Path) -> None:
    compact_text = _COMPACT_FIXTURE.read_text(encoding="utf-8")
    with patch.object(
        InstrumentLoader, "_download_compact_csv", return_value=compact_text
    ):
        with pytest.raises(FileNotFoundError):
            InstrumentLoader.load_csv_text(
                force_refresh=True,
                mcx_required=True,
                mcx_csv_path=temp_cache_dir / "missing_mcx.csv",
            )


def test_mcx_optional_skips_on_failure(temp_cache_dir: Path) -> None:
    compact_text = _COMPACT_FIXTURE.read_text(encoding="utf-8")
    with patch.object(
        InstrumentLoader, "_download_compact_csv", return_value=compact_text
    ):
        text = InstrumentLoader.load_csv_text(
            force_refresh=True,
            mcx_required=False,
            mcx_csv_path=temp_cache_dir / "missing_mcx.csv",
        )

    assert "RELIANCE" in text
    assert "GOLD" not in text


def test_resolver_loads_mcx_future_from_loader(temp_cache_dir: Path) -> None:
    compact_text = _COMPACT_FIXTURE.read_text(encoding="utf-8")
    with patch.object(
        InstrumentLoader, "_download_compact_csv", return_value=compact_text
    ):
        csv_text = InstrumentLoader.load_csv_text(
            force_refresh=True,
            mcx_csv_path=_MCX_FIXTURE,
        )

    resolver = DhanInstrumentResolver()
    resolver.load_from_csv_text(csv_text)
    ref = resolver.resolve("GOLD-05Aug2025-FUT", "MCX")
    assert ref.exchange_segment == "MCX_COMM"
    assert ref.security_id == "123456"


def test_instruments_load_force_refresh(temp_cache_dir: Path) -> None:
    from brokers.adapters.dhan.instruments import DhanInstruments

    compact_text = _COMPACT_FIXTURE.read_text(encoding="utf-8")
    resolver = DhanInstrumentResolver()
    resolver.load_from_csv_text(compact_text)

    instruments = DhanInstruments(resolver)
    with patch.object(
        InstrumentLoader,
        "load_csv_text",
        return_value=compact_text,
    ) as mock_loader:
        instruments.load(force_refresh=True)
        mock_loader.assert_called_once_with(force_refresh=True)

    info = instruments.resolve("RELIANCE", "NSE")
    assert info is not None
    assert info.symbol == "RELIANCE"
