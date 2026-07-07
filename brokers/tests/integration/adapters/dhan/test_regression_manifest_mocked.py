"""Mocked regression helper tests — run without live Dhan credentials."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from brokers.domain import MarketDepth
from brokers.domain.entities import DepthLevel, OptionChain, OptionLeg, OptionStrike

from brokers.adapters.dhan.gateway import DhanGateway
from brokers.adapters.dhan.identity import DhanInstrumentRef
from brokers.tests.integration.adapters.dhan.regression_manifest import (
    MARKET_HOURS_CASES,
    OFF_MARKET_CASES,
)


def _equity_ref(symbol: str = "RELIANCE") -> DhanInstrumentRef:
    return DhanInstrumentRef(
        symbol=symbol,
        security_id="2885",
        exchange_segment="NSE_EQ",
        instrument_type="EQUITY",
        lot_size=1,
    )


@pytest.fixture
def mock_gateway():
    with patch("brokers.adapters.dhan.auth.DhanAuth.get_token", return_value="tok"), patch(
        "brokers.adapters.dhan.gateway.JsonTokenStateStore"
    ):
        gw = DhanGateway(access_token="tok", client_id="cid", auto_refresh=False)
        yield gw
        gw.close()


class TestMockedRegressionHelpers:
    def test_architecture_cases_pass_on_mock_gateway(self, mock_gateway):
        arch_cases = [
            c
            for c in OFF_MARKET_CASES
            if "architecture" in c.tags or c.id.startswith("arch_")
        ]
        assert len(arch_cases) == 3
        for case in arch_cases:
            case.assert_fn(mock_gateway)

    def test_ltp_assertion_with_mock(self, mock_gateway):
        mock_gateway._market_data.ltp = MagicMock(return_value=Decimal("2500"))  # type: ignore[method-assign]
        case = next(c for c in OFF_MARKET_CASES if c.id == "nse_ltp")
        case.assert_fn(mock_gateway)

    def test_depth_assertion_with_mock(self, mock_gateway):
        depth = MarketDepth(
            symbol="RELIANCE",
            bids=[DepthLevel(price=Decimal("100"), quantity=10, orders=1)],
            asks=[DepthLevel(price=Decimal("101"), quantity=5, orders=1)],
        )
        mock_gateway._market_data.depth = MagicMock(return_value=depth)  # type: ignore[method-assign]
        case = next(c for c in OFF_MARKET_CASES if c.id == "nse_depth_rest")
        case.assert_fn(mock_gateway)

    def test_option_chain_assertion_with_mock(self, mock_gateway):
        leg = OptionLeg(
            ltp=Decimal("10"),
            oi=1,
            volume=1,
            iv=None,
            delta=None,
            theta=None,
            gamma=None,
            vega=None,
            security_id=1,
            symbol="NIFTY-CE",
        )
        chain = OptionChain(
            underlying="NIFTY",
            expiry="2026-07-31",
            spot=Decimal("25000"),
            strikes=[
                OptionStrike(strike=Decimal("25000"), call=leg, put=leg),
            ],
        )
        mock_gateway._options.get_expiries = MagicMock(return_value=["2026-07-31"])  # type: ignore[method-assign]
        mock_gateway._options.get_option_chain = MagicMock(return_value=chain)  # type: ignore[method-assign]
        case = next(c for c in OFF_MARKET_CASES if c.id == "nfo_option_chain_nifty")
        case.assert_fn(mock_gateway)

    def test_market_hours_case_count(self):
        assert len(MARKET_HOURS_CASES) == 2
