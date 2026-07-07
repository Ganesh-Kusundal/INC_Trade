"""Tests for ResolutionMixin — shared 3-tier instrument resolution.

Covers all 4 resolution tiers and the resolve_for_order helper.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from brokers.common.instrument_resolver import InstrumentNotFoundError
from brokers.common.resolution import ResolutionMixin
from brokers.domain.enums import Exchange, InstrumentType
from brokers.domain.instrument import Instrument
from brokers.domain.requests import OrderRequest, Side


# ── Test harness ──────────────────────────────────────────────────────────


class _FakeProvider(ResolutionMixin):
    """Minimal provider for testing the mixin."""

    def __init__(
        self,
        instruments: dict[str, str] | None = None,
        resolver: MagicMock | None = None,
        fallback_value: str = "FALLBACK",
    ) -> None:
        self._instruments = instruments or {}
        self._resolver = resolver
        self._fallback_value = fallback_value

    def _broker_fallback(self, instrument: Instrument) -> str:
        return self._fallback_value


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def provider() -> _FakeProvider:
    return _FakeProvider(
        instruments={"RELIANCE:NSE": "3456", "TCS:NSE": "7777"},
    )


@pytest.fixture
def provider_with_resolver() -> _FakeProvider:
    resolver = MagicMock()
    resolver.resolve.return_value = MagicMock(broker_id="9999")
    return _FakeProvider(
        instruments={},
        resolver=resolver,
    )


@pytest.fixture
def provider_empty() -> _FakeProvider:
    return _FakeProvider(instruments={}, resolver=None, fallback_value="FALLBACK")


# ── resolve_broker_id tests ──────────────────────────────────────────────


class TestResolveBrokerId:
    def test_tier1_security_id(self, provider: _FakeProvider) -> None:
        inst = Instrument(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            provider=provider,  # type: ignore[arg-type]
            security_id="12345",
        )
        assert provider.resolve_broker_id(inst) == "12345"

    def test_tier2_instruments_dict(self, provider: _FakeProvider) -> None:
        inst = Instrument(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            provider=provider,  # type: ignore[arg-type]
        )
        assert provider.resolve_broker_id(inst) == "3456"

    def test_tier3_resolver(self, provider_with_resolver: _FakeProvider) -> None:
        inst = Instrument(
            symbol="INFY",
            exchange=Exchange.NSE,
            provider=provider_with_resolver,  # type: ignore[arg-type]
        )
        result = provider_with_resolver.resolve_broker_id(inst)
        assert result == "9999"
        provider_with_resolver._resolver.resolve.assert_called_once_with(
            "INFY", Exchange.NSE
        )

    def test_tier4_fallback(self, provider_empty: _FakeProvider) -> None:
        inst = Instrument(
            symbol="UNKNOWN",
            exchange=Exchange.NSE,
            provider=provider_empty,  # type: ignore[arg-type]
        )
        assert provider_empty.resolve_broker_id(inst) == "FALLBACK"

    def test_resolver_not_found_falls_through(
        self, provider_empty: _FakeProvider
    ) -> None:
        resolver = MagicMock()
        resolver.resolve.side_effect = InstrumentNotFoundError("X", "NSE", "test")
        provider_empty._resolver = resolver

        inst = Instrument(
            symbol="UNKNOWN",
            exchange=Exchange.NSE,
            provider=provider_empty,  # type: ignore[arg-type]
        )
        assert provider_empty.resolve_broker_id(inst) == "FALLBACK"

    def test_empty_instruments_dict(self) -> None:
        provider = _FakeProvider(instruments={}, resolver=None)
        inst = Instrument(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            provider=provider,  # type: ignore[arg-type]
        )
        assert provider.resolve_broker_id(inst) == "FALLBACK"

    def test_tier1_beats_tier2(self, provider: _FakeProvider) -> None:
        inst = Instrument(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            provider=provider,  # type: ignore[arg-type]
            security_id="OVERRIDE",
        )
        assert provider.resolve_broker_id(inst) == "OVERRIDE"


# ── resolve_for_order tests ──────────────────────────────────────────────


class TestResolveForOrder:
    def test_with_instrument_attached(self, provider: _FakeProvider) -> None:
        inst = Instrument(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            provider=provider,  # type: ignore[arg-type]
        )
        request = OrderRequest(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            side=Side.BUY,
            quantity=10,
            instrument=inst,
        )
        assert provider.resolve_for_order(request) == "3456"

    def test_without_instrument_dict_hit(self, provider: _FakeProvider) -> None:
        request = OrderRequest(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            side=Side.BUY,
            quantity=10,
        )
        assert provider.resolve_for_order(request) == "3456"

    def test_without_instrument_resolver_hit(
        self, provider_with_resolver: _FakeProvider
    ) -> None:
        request = OrderRequest(
            symbol="INFY",
            exchange=Exchange.NSE,
            side=Side.BUY,
            quantity=10,
        )
        assert provider_with_resolver.resolve_for_order(request) == "9999"

    def test_without_instrument_fallback(self, provider_empty: _FakeProvider) -> None:
        request = OrderRequest(
            symbol="UNKNOWN",
            exchange=Exchange.NSE,
            side=Side.BUY,
            quantity=10,
        )
        assert provider_empty.resolve_for_order(request) == "FALLBACK"

    def test_without_instrument_tier1_on_request(
        self, provider: _FakeProvider
    ) -> None:
        inst = Instrument(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            provider=provider,  # type: ignore[arg-type]
            security_id="EXPLICIT",
        )
        request = OrderRequest(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            side=Side.BUY,
            quantity=10,
            instrument=inst,
        )
        assert provider.resolve_for_order(request) == "EXPLICIT"
