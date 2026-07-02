"""Upstox mock broker factory for contract tests."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock


def make_mock_broker(**kwargs: Any) -> MagicMock:
    """Create a mock Upstox broker for contract testing."""
    mock = MagicMock()
    mock.name = "upstox"
    return mock
