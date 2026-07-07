"""Shared instrument resolution mixin for broker providers.

Eliminates the duplicated 3-tier resolution pattern across brokers:

  Tier 1: instrument.security_id (already resolved)
  Tier 2: self._instruments dict (manual symbol→ID mapping)
  Tier 3: self._resolver.resolve() (CSV/JSON instrument master)
  Tier 4: _broker_fallback() (broker-specific default)

Usage::

    class DhanProvider(ResolutionMixin):
        def _broker_fallback(self, instrument):
            return instrument.symbol  # Dhan expects numeric, but this is the last resort

    class UpstoxProvider(ResolutionMixin):
        def _broker_fallback(self, instrument):
            return _instrument_key(instrument.symbol, instrument.exchange)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from brokers.common.instrument_resolver import InstrumentNotFoundError
from brokers.domain.enums import Exchange

if TYPE_CHECKING:
    from brokers.common.instrument_resolver import InstrumentResolver
    from brokers.domain.instrument import Instrument
    from brokers.domain.requests import OrderRequest


class ResolutionMixin:
    """3-tier instrument resolution mixin for broker providers.

    Provides ``resolve_broker_id`` for general use and ``resolve_for_order``
    which additionally handles the case where ``OrderRequest.instrument`` is None.
    """

    _instruments: dict[str, str]
    _resolver: InstrumentResolver | None

    def resolve_broker_id(self, instrument: Instrument) -> str:
        """Resolve an Instrument to its broker-native ID.

        Tries tiers 1–3, then falls back to ``_broker_fallback``.
        """
        # Tier 1: already resolved on the Instrument object
        if instrument.security_id:
            return instrument.security_id

        # Tier 2: manual mapping dict
        key = f"{instrument.symbol}:{instrument.exchange.value}"
        sid = self._instruments.get(key)
        if sid:
            return sid

        # Tier 3: resolver (CSV/JSON instrument master)
        if self._resolver is not None:
            try:
                resolved = self._resolver.resolve(
                    instrument.symbol, instrument.exchange
                )
                return resolved.broker_id
            except InstrumentNotFoundError:
                pass

        # Tier 4: broker-specific fallback
        return self._broker_fallback(instrument)

    def resolve_for_order(self, request: OrderRequest) -> str:
        """Resolve security_id for order placement.

        Handles both cases:
        - ``request.instrument`` is set → delegate to ``resolve_broker_id``
        - ``request.instrument`` is None → try dict, resolver, then fallback
        """
        if request.instrument is not None:
            return self.resolve_broker_id(request.instrument)

        # No instrument attached — try tiers 2–4 inline
        key = f"{request.symbol}:{request.exchange.value}"
        sid = self._instruments.get(key)
        if sid:
            return sid

        if self._resolver is not None:
            try:
                from brokers.domain.instrument import Instrument

                tmp = Instrument(
                    symbol=request.symbol,
                    exchange=request.exchange,
                    provider=self,
                )
                return self.resolve_broker_id(tmp)
            except Exception:
                pass

        return self._broker_fallback_for_symbol(
            request.symbol, request.exchange
        )

    def _broker_fallback(self, instrument: Instrument) -> str:
        """Broker-specific fallback when all resolution tiers fail.

        MUST be overridden by each provider subclass.
        """
        raise NotImplementedError(
            f"{type(self).__name__} must implement _broker_fallback"
        )

    def _broker_fallback_for_symbol(
        self, symbol: str, exchange: Exchange
    ) -> str:
        """Fallback when no Instrument object is available.

        Builds a temporary Instrument and delegates to ``_broker_fallback``.
        """
        from brokers.domain.instrument import Instrument

        tmp = Instrument(
            symbol=symbol,
            exchange=exchange,
            provider=self,  # type: ignore[arg-type]
        )
        return self._broker_fallback(tmp)


__all__ = ["ResolutionMixin"]
