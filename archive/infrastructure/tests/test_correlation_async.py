"""Tests for infrastructure.correlation — async context isolation (Fix #9)."""

from __future__ import annotations

import asyncio

import pytest

from infrastructure.correlation import (
    get_current_correlation_id,
    set_current_correlation_id,
    with_correlation,
)


class TestCorrelationContextVar:
    """Fix #9: correlation IDs must not leak across async tasks."""

    @pytest.mark.asyncio
    async def test_no_cross_contamination_between_tasks(self):
        """Two concurrent async tasks must see their own correlation IDs."""
        results = {}

        async def task_a():
            set_current_correlation_id("task-a-id")
            await asyncio.sleep(0.01)
            results["a"] = get_current_correlation_id()

        async def task_b():
            set_current_correlation_id("task-b-id")
            await asyncio.sleep(0.01)
            results["b"] = get_current_correlation_id()

        await asyncio.gather(task_a(), task_b())

        assert results["a"] == "task-a-id"
        assert results["b"] == "task-b-id"

    @pytest.mark.asyncio
    async def test_default_is_none(self):
        """Unset correlation ID returns None."""
        # In a fresh context, should be None
        set_current_correlation_id(None)
        assert get_current_correlation_id() is None

    def test_with_correlation_context_manager(self):
        """with_correlation sets and restores the ID."""
        assert get_current_correlation_id() is None
        with with_correlation("test-id") as cid:
            assert cid == "test-id"
            assert get_current_correlation_id() == "test-id"
        assert get_current_correlation_id() is None

    def test_set_and_get(self):
        """Basic set/get round-trip."""
        set_current_correlation_id("hello")
        assert get_current_correlation_id() == "hello"
        set_current_correlation_id(None)
