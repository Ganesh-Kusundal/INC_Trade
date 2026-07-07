"""Unit tests verifying Instrument type-detection is content-based and broker-agnostic.

The detection logic in :mod:`brokers.market.instrument` must not depend
on broker-specific segment strings (e.g., ``"NSE_EQ"``, ``"NSE_FNO"``,
``"NSE_INDEX"``). It should work purely from the canonical fields
``exchange``, ``option_type``, ``strike``, ``expiry``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from brokers.market.instrument import Instrument


class TestContentBasedDetection:
    def test_equity_on_nse(self) -> None:
        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        assert inst.is_equity() is True
        assert inst.is_future() is False
        assert inst.is_option() is False

    def test_equity_with_dhan_segment(self) -> None:
        """Even with Dhan segment, type detection works on content."""
        inst = Instrument(symbol="RELIANCE", exchange="NSE", segment="NSE_EQ")
        assert inst.is_equity() is True

    def test_future_detected_by_exchange_and_expiry(self) -> None:
        inst = Instrument(
            symbol="NIFTY FUT",
            exchange="NFO",
            expiry=datetime(2025, 1, 30, tzinfo=UTC),
        )
        assert inst.is_future() is True
        assert inst.is_equity() is False
        assert inst.is_option() is False

    def test_option_detected_by_type_and_strike(self) -> None:
        inst = Instrument(
            symbol="NIFTY 18000 CE",
            exchange="NFO",
            option_type="CE",
            strike=Decimal("18000"),
        )
        assert inst.is_option() is True
        assert inst.is_call() is True
        assert inst.is_put() is False
        assert inst.is_future() is False

    def test_put_option(self) -> None:
        inst = Instrument(
            symbol="NIFTY 18000 PE",
            exchange="NFO",
            option_type="PE",
            strike=Decimal("18000"),
        )
        assert inst.is_option() is True
        assert inst.is_put() is True

    def test_future_with_strike_is_not_a_future(self) -> None:
        """Strike + expiry + no option_type = malformed; not a future."""
        inst = Instrument(
            symbol="X",
            exchange="NFO",
            expiry=datetime(2025, 1, 30, tzinfo=UTC),
            strike=Decimal("100"),
        )
        assert inst.is_future() is False

    def test_segment_string_does_not_affect_type(self) -> None:
        """Setting segment to any string must not affect type detection."""
        for segment in ("", "NSE_EQ", "NSE_FNO", "NSE_FUT", "BSE_FUT", "NSE_INDEX", "WHATEVER"):
            inst = Instrument(
                symbol="RELIANCE",
                exchange="NSE",
                segment=segment,
            )
            assert inst.is_equity() is True, f"segment={segment!r}"

    def test_derivative_exchanges_detected(self) -> None:
        for ex in ("NFO", "BFO", "CDS", "BCD"):
            inst = Instrument(
                symbol="X",
                exchange=ex,
                expiry=datetime(2025, 1, 30, tzinfo=UTC),
            )
            assert inst.is_future() is True, f"exchange={ex!r}"

    def test_index_heuristic_no_isin(self) -> None:
        """Heuristic: equity on NSE/BSE with no ISIN looks like an index."""
        inst = Instrument(symbol="NIFTY", exchange="NSE", name="NIFTY 50")
        assert inst.is_index() is True

    def test_equity_with_isin_is_not_index(self) -> None:
        inst = Instrument(
            symbol="RELIANCE",
            exchange="NSE",
            isin="INE002A01018",
        )
        assert inst.is_index() is False
