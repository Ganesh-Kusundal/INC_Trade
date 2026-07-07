"""Tests for domain extension entities — alerts, result, exchange_segments, symbols."""

from __future__ import annotations

from decimal import Decimal

import pytest

from brokers.domain.alerts import (
    ConditionalAlert,
    ConditionalAlertRequest,
    MarketIntelligenceSnapshot,
    PnlExitPolicy,
    PnlExitResult,
)
from brokers.domain.result import GatewayResult, ResultMetadata
from brokers.domain.exchange_segments import (
    ExchangeSegment,
    canonical_exchange_short,
    is_commodity_segment,
    is_currency_segment,
    is_derivative_segment,
    is_equity_segment,
    parse_segment,
    wire_value,
)
from brokers.domain.symbols import (
    make_instrument_key,
    make_position_key,
    normalize_exchange,
    normalize_symbol,
)


# ── Alert entities ──────────────────────────────────────────────────────


class TestConditionalAlert:
    def test_frozen(self) -> None:
        alert = ConditionalAlert(alert_id="a1", symbol="RELIANCE", condition="LTP > 2500")
        assert alert.alert_id == "a1"
        assert alert.status == "ACTIVE"

    def test_defaults(self) -> None:
        alert = ConditionalAlert()
        assert alert.alert_id == ""
        assert alert.status == "ACTIVE"


class TestConditionalAlertRequest:
    def test_frozen(self) -> None:
        req = ConditionalAlertRequest(symbol="RELIANCE", exchange="NSE", threshold=Decimal("2500"))
        assert req.symbol == "RELIANCE"
        assert req.threshold == Decimal("2500")


class TestMarketIntelligenceSnapshot:
    def test_mutable_oi_data(self) -> None:
        snap = MarketIntelligenceSnapshot(underlying="RELIANCE")
        snap.oi_data["CE"] = 1000
        assert snap.oi_data["CE"] == 1000


class TestPnlExitPolicy:
    def test_frozen(self) -> None:
        policy = PnlExitPolicy(target_pnl=Decimal("5000"), stop_loss=Decimal("-2000"))
        assert policy.target_pnl == Decimal("5000")


class TestPnlExitResult:
    def test_success(self) -> None:
        result = PnlExitResult(success=True, message="Exited")
        assert result.success is True


# ── GatewayResult monad ─────────────────────────────────────────────────


class TestResultMetadata:
    def test_defaults(self) -> None:
        meta = ResultMetadata()
        assert meta.source == ""
        assert meta.latency_ms == 0.0


class TestGatewayResultSuccess:
    def test_success_factory(self) -> None:
        result = GatewayResult.success(42)
        assert result.is_success is True
        assert result.value == 42
        assert result.error is None

    def test_bool_true(self) -> None:
        assert bool(GatewayResult.success("ok")) is True

    def test_str(self) -> None:
        result = GatewayResult.success(42)
        assert "Success" in str(result)


class TestGatewayResultFailure:
    def test_failure_factory(self) -> None:
        result = GatewayResult.failure("boom")
        assert result.is_success is False
        assert result.is_failure is True
        assert result.error == "boom"

    def test_bool_false(self) -> None:
        assert bool(GatewayResult.failure("err")) is False

    def test_str(self) -> None:
        result = GatewayResult.failure("boom")
        assert "Failure" in str(result)


class TestGatewayResultMap:
    def test_map_success(self) -> None:
        result: GatewayResult[int] = GatewayResult.success(10).map(lambda x: x * 2)
        assert result.value == 20

    def test_map_failure_passthrough(self) -> None:
        result: GatewayResult[int] = GatewayResult.failure("err").map(lambda x: x * 2)
        assert result.is_failure

    def test_map_exception(self) -> None:
        result: GatewayResult[int] = GatewayResult.success(10).map(lambda x: x / 0)
        assert result.is_failure


class TestGatewayResultFlatMap:
    def test_flat_map_success(self) -> None:
        result: GatewayResult[int] = GatewayResult.success(10).flat_map(lambda x: GatewayResult.success(x + 5))
        assert result.value == 15

    def test_flat_map_to_failure(self) -> None:
        result: GatewayResult[int] = GatewayResult.success(10).flat_map(lambda x: GatewayResult.failure("nope"))
        assert result.is_failure

    def test_flat_map_exception(self) -> None:
        result: GatewayResult[int] = GatewayResult.success(10).flat_map(lambda x: (_ for _ in ()).throw(RuntimeError("boom")))
        assert result.is_failure


class TestGatewayResultRecover:
    def test_recover_from_failure(self) -> None:
        result: GatewayResult[int] = GatewayResult.failure("err").recover(lambda e: 99)
        assert result.value == 99
        assert result.is_success

    def test_recover_noop_on_success(self) -> None:
        result: GatewayResult[int] = GatewayResult.success(42).recover(lambda e: 99)
        assert result.value == 42


class TestGatewayResultGetOrElse:
    def test_get_or_else_success(self) -> None:
        assert GatewayResult.success(42).get_or_else(0) == 42

    def test_get_or_else_failure(self) -> None:
        assert GatewayResult.failure("err").get_or_else(0) == 0


# ── Exchange segments ──────────────────────────────────────────────────


class TestParseSegment:
    def test_nse_alias(self) -> None:
        assert parse_segment("NSE") == ExchangeSegment.NSE

    def test_nfo_alias(self) -> None:
        assert parse_segment("nfo") == ExchangeSegment.NSE_FNO

    def test_mcx_alias(self) -> None:
        assert parse_segment("MCX") == ExchangeSegment.MCX

    def test_enum_passthrough(self) -> None:
        assert parse_segment(ExchangeSegment.BSE) == ExchangeSegment.BSE

    def test_unknown_returns_default(self) -> None:
        assert parse_segment("UNKNOWN") is None

    def test_unknown_with_default(self) -> None:
        result = parse_segment("UNKNOWN", default=ExchangeSegment.NSE)
        assert result == ExchangeSegment.NSE

    def test_case_insensitive(self) -> None:
        assert parse_segment("nse") == ExchangeSegment.NSE
        assert parse_segment("Nfo") == ExchangeSegment.NSE_FNO


class TestSegmentClassification:
    def test_equity(self) -> None:
        assert is_equity_segment("NSE") is True
        assert is_equity_segment("BSE") is True
        assert is_equity_segment("NFO") is False

    def test_derivative(self) -> None:
        assert is_derivative_segment("NFO") is True
        assert is_derivative_segment("MCX") is True
        assert is_derivative_segment("NSE") is False

    def test_currency(self) -> None:
        assert is_currency_segment("CDS") is True
        assert is_currency_segment("BCD") is True
        assert is_currency_segment("NSE") is False

    def test_commodity(self) -> None:
        assert is_commodity_segment("MCX") is True
        assert is_commodity_segment("NSE") is False


class TestWireValue:
    def test_nse(self) -> None:
        assert wire_value("NSE") == "NSE_EQ"

    def test_nfo(self) -> None:
        assert wire_value("NFO") == "NSE_FNO"

    def test_unknown_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown exchange segment"):
            wire_value("UNKNOWN")


class TestCanonicalExchangeShort:
    def test_nse(self) -> None:
        assert canonical_exchange_short("NSE") == "NSE"

    def test_nfo(self) -> None:
        assert canonical_exchange_short("NFO") == "NFO"

    def test_unknown_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown exchange segment"):
            canonical_exchange_short("UNKNOWN")


# ── Symbol normalization ────────────────────────────────────────────────


class TestNormalizeSymbol:
    def test_strips_and_uppercases(self) -> None:
        assert normalize_symbol("  Reliance  ") == "RELIANCE"

    def test_already_normalized(self) -> None:
        assert normalize_symbol("RELIANCE") == "RELIANCE"

    def test_lowercase(self) -> None:
        assert normalize_symbol("reliance") == "RELIANCE"


class TestNormalizeExchange:
    def test_strips_and_uppercases(self) -> None:
        assert normalize_exchange("  nse  ") == "NSE"

    def test_already_normalized(self) -> None:
        assert normalize_exchange("NSE") == "NSE"


class TestMakePositionKey:
    def test_format(self) -> None:
        assert make_position_key("RELIANCE", "NSE") == "RELIANCE:NSE"

    def test_normalizes(self) -> None:
        assert make_position_key("  reliance  ", "  nse  ") == "RELIANCE:NSE"


class TestMakeInstrumentKey:
    def test_format(self) -> None:
        assert make_instrument_key("RELIANCE", "NSE") == ("RELIANCE", "NSE")

    def test_normalizes(self) -> None:
        assert make_instrument_key("reliance", "nse") == ("RELIANCE", "NSE")
