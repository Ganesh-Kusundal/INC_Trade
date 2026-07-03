"""Instrument catalog loader — streams complete.json.gz from Upstox CDN."""

from __future__ import annotations

import gzip
import json
import logging
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import IO

import requests

from brokers.adapters.upstox.instrument_definition import UpstoxInstrumentDefinition

logger = logging.getLogger(__name__)

COMPLETE_JSON_URL = (
    "https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz"
)
CACHE_VALIDITY_HOURS = 24


class UpstoxInstrumentLoader:
    def __init__(self, *, timeout_seconds: int = 60) -> None:
        self._timeout = timeout_seconds

    def download(self, cache_path: Path) -> Path:
        cache_path = Path(cache_path)
        if self._is_cache_valid(cache_path):
            logger.debug("Using cached instruments (valid for 24h)")
            return cache_path

        logger.info("Downloading fresh instrument catalog from Upstox...")
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        start = time.time()
        with requests.get(COMPLETE_JSON_URL, stream=True, timeout=self._timeout) as resp:
            resp.raise_for_status()
            with open(cache_path, "wb") as fp:
                for chunk in resp.iter_content(chunk_size=64 * 1024):
                    if chunk:
                        fp.write(chunk)
        elapsed = time.time() - start
        file_size_mb = cache_path.stat().st_size / (1024 * 1024)
        logger.info(
            "Instrument catalog downloaded: %.1fMB in %.1fs", file_size_mb, elapsed
        )
        return cache_path

    def load(self, path: Path) -> list[UpstoxInstrumentDefinition]:
        path = Path(path)
        json_gz_path = path.with_name(path.stem + ".parsed.json.gz")
        pkl_path = path.with_suffix(".pkl")

        if pkl_path.exists() and not json_gz_path.exists():
            self._quarantine_pickle(pkl_path)

        if self._is_json_cache_valid(path, json_gz_path):
            try:
                return self._load_json_cache(json_gz_path)
            except Exception as exc:
                logger.warning("JSON cache load failed: %s", exc)

        defs = list(self.iter_definitions(path))
        try:
            self._save_json_cache(defs, json_gz_path)
        except Exception as exc:
            logger.warning("Failed to save JSON cache: %s", exc)
        return defs

    def iter_definitions(self, path: Path) -> Iterator[UpstoxInstrumentDefinition]:
        path = Path(path)
        opener: Callable[[], IO[str]]
        if str(path).endswith(".gz"):
            opener = lambda: gzip.open(path, "rt", encoding="utf-8")
        else:
            opener = lambda: open(path, encoding="utf-8")

        with opener() as fp:
            try:
                data = json.load(fp)
            except json.JSONDecodeError:
                logger.exception("Failed to parse instrument file %s", path)
                return

        if isinstance(data, list):
            for record in data:
                if isinstance(record, dict):
                    try:
                        yield UpstoxInstrumentDefinition.from_dict(record)
                    except (ValueError, TypeError):
                        logger.debug("Skipping malformed record", exc_info=True)
            return

        if isinstance(data, dict):
            for record in data.values():
                if isinstance(record, dict):
                    try:
                        yield UpstoxInstrumentDefinition.from_dict(record)
                    except (ValueError, TypeError):
                        continue

    def _is_cache_valid(self, cache_path: Path) -> bool:
        if not cache_path.exists():
            return False
        age_hours = (time.time() - cache_path.stat().st_mtime) / 3600
        return age_hours < CACHE_VALIDITY_HOURS

    def _is_json_cache_valid(self, json_path: Path, json_gz_path: Path) -> bool:
        if not json_gz_path.exists():
            return False
        if not json_path.exists():
            return True
        return json_gz_path.stat().st_mtime >= json_path.stat().st_mtime

    def _load_json_cache(self, json_gz_path: Path) -> list[UpstoxInstrumentDefinition]:
        with gzip.open(json_gz_path, "rt", encoding="utf-8") as f:
            data = json.load(f)
        return [UpstoxInstrumentDefinition(**item) for item in data]

    def _save_json_cache(
        self, defs: list[UpstoxInstrumentDefinition], json_gz_path: Path
    ) -> None:
        data = [d.to_dict() for d in defs]
        with gzip.open(json_gz_path, "wt", encoding="utf-8") as f:
            json.dump(data, f, separators=(",", ":"))

    @staticmethod
    def _quarantine_pickle(pkl_path: Path) -> None:
        quarantine = pkl_path.with_suffix(pkl_path.suffix + ".quarantine")
        try:
            pkl_path.rename(quarantine)
            logger.info("Quarantined legacy pickle cache: %s", quarantine)
        except Exception as exc:
            logger.error("Failed to quarantine pickle cache: %s", exc)
