"""Shared parallel batch execution for broker and datalake gateways."""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TypeVar

from domain.constants import BATCH_MAX_WORKERS

logger = logging.getLogger(__name__)

T = TypeVar("T")


def batch_execute(
    items: list[str],
    fn: Callable[[str], T],
    *,
    max_workers: int = BATCH_MAX_WORKERS,
    on_error: Callable[[str, Exception], None] | None = None,
) -> dict[str, T]:
    """Execute *fn* for each item in parallel; omit failed items from results."""
    if not items:
        return {}

    results: dict[str, T] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_item = {executor.submit(fn, item): item for item in items}
        for future in as_completed(future_to_item):
            item = future_to_item[future]
            try:
                results[item] = future.result()
            except Exception as exc:
                if on_error is not None:
                    on_error(item, exc)
                else:
                    logger.debug("batch_execute failed for %s: %s", item, exc)
    return results
