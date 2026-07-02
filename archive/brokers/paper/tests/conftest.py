"""Shared test fixtures for brokers.paper tests.

Provides PaperGateway fixtures, seeded mock brokers, and trading contexts
for deterministic testing without external dependencies.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from brokers.paper.mock_broker import create_demo_broker
from brokers.paper.paper_gateway import PaperGateway
from tests.e2e.fixtures.trading_context_factory import create_paper_trading_context

# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def paper_gateway():
    """Provide a PaperGateway instance with default capital."""
    return PaperGateway(initial_capital=Decimal("1000000"))


@pytest.fixture
def paper_gateway_small_capital():
    """Provide a PaperGateway with small capital for testing risk limits."""
    return PaperGateway(initial_capital=Decimal("10000"))


@pytest.fixture
def seeded_paper_broker():
    """Provide a MockBroker pre-populated with realistic seed data.

    Uses create_demo_broker() from brokers.paper.mock_broker
    to create a broker with pre-seeded orders, trades, positions, and holdings.
    """
    return create_demo_broker(name="paper", initial_capital=Decimal("1000000"))


@pytest.fixture
def paper_trading_context():
    """Provide a TradingContext configured for paper trading.

    Uses create_paper_trading_context() with permissive risk limits
    suitable for testing trading flows without restrictions.
    """
    return create_paper_trading_context(
        capital=Decimal("100000"),
        max_position_pct=Decimal("25"),
        max_gross_pct=Decimal("100"),
        max_daily_loss_pct=Decimal("5"),
    )


@pytest.fixture
def paper_trading_context_strict():
    """Provide a TradingContext with strict risk limits for testing rejections."""
    return create_paper_trading_context(
        capital=Decimal("100000"),
        max_position_pct=Decimal("5"),
        max_gross_pct=Decimal("50"),
        max_daily_loss_pct=Decimal("1"),
    )
