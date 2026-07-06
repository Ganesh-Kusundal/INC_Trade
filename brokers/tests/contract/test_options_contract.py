"""Contract tests — verify any options adapter satisfies the OptionsPort protocol."""

from __future__ import annotations

from decimal import Decimal

import pytest
from inc_trade.domain import OptionChain, OptionLeg, OptionStrike
from inc_trade.ports import OptionsPort


def _make_fake_leg() -> OptionLeg:
    return OptionLeg(
        ltp=Decimal("100"),
        oi=1000,
        volume=500,
        iv=Decimal("0.25"),
        delta=Decimal("0.5"),
        theta=Decimal("-0.1"),
        gamma=Decimal("0.02"),
        vega=Decimal("0.15"),
        security_id=0,
        symbol="NIFTY24JAN25CE18000",
    )


class _FakeOptions:
    def get_expiries(self, underlying: str, exchange: str = "NFO") -> list[str]:
        return ["2024-01-25", "2024-02-28"]

    def get_option_chain(
        self,
        underlying: str,
        exchange: str = "NFO",
        expiry: str | None = None,
    ) -> OptionChain:
        leg = _make_fake_leg()
        return OptionChain(
            underlying=underlying,
            expiry=expiry or "2024-01-25",
            spot=Decimal("22000"),
            strikes=(OptionStrike(strike=Decimal("18000"), call=leg, put=leg),),
        )


@pytest.mark.contract
class TestOptionsContract:
    def test_satisfies_protocol(self):
        adapter = _FakeOptions()
        assert isinstance(adapter, OptionsPort)

    def test_get_expiries_returns_list(self):
        adapter = _FakeOptions()
        result = adapter.get_expiries("NIFTY")
        assert isinstance(result, list)
        assert len(result) > 0

    def test_get_option_chain_returns_option_chain(self):
        adapter = _FakeOptions()
        result = adapter.get_option_chain("NIFTY")
        assert isinstance(result, OptionChain)
        assert result.underlying == "NIFTY"

    def test_get_option_chain_with_expiry(self):
        adapter = _FakeOptions()
        result = adapter.get_option_chain("NIFTY", expiry="2024-02-28")
        assert isinstance(result, OptionChain)
        assert result.expiry == "2024-02-28"
