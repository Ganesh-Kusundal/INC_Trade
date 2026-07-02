"""Unit tests for the OmsOrderCommand correlation_id requirement."""

from __future__ import annotations

import os

import pytest

from application.oms.order_manager import OmsOrderCommand
from domain import Side


class TestCorrelationIdRequirement:
    def test_no_correlation_id_raises_outside_pytest(self, monkeypatch) -> None:
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        with pytest.raises(ValueError, match="correlation_id is required"):
            OmsOrderCommand(
                symbol="RELIANCE",
                exchange="NSE",
                side=Side.BUY,
                quantity=10,
            )

    def test_explicit_correlation_id_accepted(self) -> None:
        cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            correlation_id="ord:abc-123",
        )
        assert cmd.correlation_id == "ord:abc-123"

    def test_pytest_auto_generates_correlation_id(self) -> None:
        assert os.getenv("PYTEST_CURRENT_TEST"), "must run under pytest"
        cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
        )
        assert cmd.correlation_id.startswith("test:")
