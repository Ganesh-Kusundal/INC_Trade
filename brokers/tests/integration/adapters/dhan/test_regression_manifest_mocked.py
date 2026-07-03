"""Mocked regression helper tests — run without live Dhan credentials."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from brokers.adapters.dhan.compat_gateway import (
    DhanCompatibilityGateway,
    FutureChain,
)
from brokers.adapters.dhan.gateway import DhanGateway
from brokers.adapters.dhan.identity import DhanInstrumentRef
from brokers.adapters.dhan.options import OptionChain, OptionLeg, OptionStrike
from brokers.domain import Balance, MarketDepth, Quote
from brokers.domain.entities import DepthLevel
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
def mock_compat_gateway():
    with patch("brokers.adapters.dhan.auth.DhanAuth.get_token", return_value="tok"), patch(
        "brokers.adapters.dhan.gateway.JsonTokenStateStore"
    ):
        gw = DhanGateway(access_token="tok", client_id="cid", auto_refresh=False)
        compat = DhanCompatibilityGateway(gw)
        yield compat
        compat.close()


class TestMockedRegressionHelpers:
    def test_architecture_cases_pass_on_mock_gateway(self, mock_compat_gateway):
        arch_cases = [
            c
            for c in OFF_MARKET_CASES
            if "architecture" in c.tags or c.id.startswith("arch_")
        ]
        assert len(arch_cases) == 3
        for case in arch_cases:
            case.assert_fn(mock_compat_gateway)

    def test_ltp_assertion_with_mock(self, mock_compat_gateway):
        mock_compat_gateway._gw.market_data.ltp = MagicMock(return_value=Decimal("2500"))  # type: ignore[method-assign]
        case = next(c for c in OFF_MARKET_CASES if c.id == "nse_ltp")
        case.assert_fn(mock_compat_gateway)

    def test_depth_assertion_with_mock(self, mock_compat_gateway):
        depth = MarketDepth(
            symbol="RELIANCE",
            bids=[DepthLevel(price=Decimal("100"), quantity=10, orders=1)],
            asks=[DepthLevel(price=Decimal("101"), quantity=5, orders=1)],
        )
        mock_compat_gateway._gw.market_data.depth = MagicMock(return_value=depth)  # type: ignore[method-assign]
        case = next(c for c in OFF_MARKET_CASES if c.id == "nse_depth_rest")
        case.assert_fn(mock_compat_gateway)

    def test_history_assertion_with_mock(self, mock_compat_gateway):
        mock_compat_gateway.history = MagicMock(  # type: ignore[method-assign]
            return_value=pd.DataFrame(
                [{"open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 100}]
            )
        )
        case = next(c for c in OFF_MARKET_CASES if c.id == "nse_history_daily")
        case.assert_fn(mock_compat_gateway)

    def test_option_chain_assertion_with_mock(self, mock_compat_gateway):
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
        mock_compat_gateway.option_chain = MagicMock(return_value=chain)  # type: ignore[method-assign]
        case = next(c for c in OFF_MARKET_CASES if c.id == "nfo_option_chain_nifty")
        case.assert_fn(mock_compat_gateway)

    def test_future_chain_assertion_with_mock(self, mock_compat_gateway):
        from brokers.adapters.dhan.compat_gateway import FutureContract

        fc = FutureChain(
            underlying="NIFTY",
            exchange="NFO",
            contracts=(
                FutureContract(
                    symbol="NIFTY-FUT",
                    expiry="2026-07-31",
                    underlying="NIFTY",
                ),
            ),
        )
        mock_compat_gateway.future_chain = MagicMock(return_value=fc)  # type: ignore[method-assign]
        case = next(c for c in OFF_MARKET_CASES if c.id == "nfo_future_chain_nifty")
        case.assert_fn(mock_compat_gateway)

    def test_market_hours_case_count(self):
        assert len(MARKET_HOURS_CASES) == 2
