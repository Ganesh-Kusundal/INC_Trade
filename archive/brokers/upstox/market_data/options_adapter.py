"""Upstox options adapter — implements ``OptionsProvider`` port."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from brokers.common.gateway_interfaces import OptionsProvider
from brokers.upstox.mappers.domain_mapper import UpstoxDomainMapper
from brokers.upstox.market_data.options_client import UpstoxOptionsClient
from domain import OptionContract

if TYPE_CHECKING:
    from brokers.upstox.instruments.resolver import UpstoxInstrumentResolver

logger = logging.getLogger(__name__)


class UpstoxOptionsAdapter(OptionsProvider):
    def __init__(
        self,
        client: UpstoxOptionsClient,
        instrument_resolver: UpstoxInstrumentResolver | None = None,
    ) -> None:
        self._client = client
        self._resolver = instrument_resolver

    def get_expiries(self, underlying: str, exchange_segment: str) -> list[str]:
        """Return future-dated option expiries for *underlying*.

        Derives from the in-memory instrument master. Raises
        :class:`RuntimeError` if instruments are not loaded — the legacy
        ``/v2/option/expiry`` endpoint is deprecated and returns HTTP 400.
        """
        if self._resolver is None:
            raise RuntimeError("Upstox instruments not loaded; cannot derive option expiries")
        return self._resolver.list_option_expiries(underlying)

    def _resolve_instrument(self, underlying: str, exchange_segment: str) -> str:
        """Resolve underlying symbol to Upstox ``instrument_key``.

        Order (single source of truth — mirrors ``SymbolResolverAdapter``):
        1. ``config.indices.index_upstox_key`` for known indices.
        2. ``instrument_resolver.resolve`` with normalized segment
           (e.g. ``INDEX`` → ``NSE_INDEX``).
        3. Hard fail with a clear message — never synthesize invalid keys.
        """
        from config.indices import index_upstox_key

        idx_key = index_upstox_key(underlying)
        if idx_key is not None:
            return idx_key

        if self._resolver is not None:
            # Normalize segment: callers often pass "INDEX" but Upstox
            # instrument records use "NSE_INDEX" / "BSE_INDEX".
            from config.indices import upstox_index_segment

            seg = exchange_segment
            if underlying.upper() in {
                "NIFTY",
                "BANKNIFTY",
                "FINNIFTY",
                "MIDCPNIFTY",
                "SENSEX",
                "BANKEX",
                "NIFTY50",
                "NIFTYBANK",
            }:
                normalized = upstox_index_segment(underlying)
                if normalized:
                    seg = normalized
            defn = self._resolver.resolve(symbol=underlying, exchange_segment=seg)
            if defn is not None:
                return defn.instrument_key

        raise ValueError(
            f"Cannot resolve Upstox instrument_key for underlying={underlying!r} "
            f"exchange_segment={exchange_segment!r}. Ensure instruments are "
            f"loaded (load_instruments=True) and the symbol/segment are valid."
        )

    def get_option_chain(
        self, underlying: str, exchange_segment: str, expiry: str
    ) -> list[OptionContract]:
        instrument_key = self._resolve_instrument(underlying, exchange_segment)
        body = self._client.get_chain(instrument_key, expiry)
        if not isinstance(body, dict) or body.get("status") != "success":
            logger.warning(
                "upstox_option_chain_non_success",
                extra={"underlying": underlying, "expiry": expiry, "body": body},
            )
            return []
        data = body.get("data")
        if not isinstance(data, list):
            return []
        out: list[OptionContract] = []
        for row in data:
            if isinstance(row, dict):
                out.append(UpstoxDomainMapper.to_option_contract(row))
        return out

    def get_option_chain_with_meta(
        self, underlying: str, exchange_segment: str, expiry: str
    ) -> tuple[list[OptionContract], list[dict], dict]:
        """Like :meth:`get_option_chain` but also returns the raw chain rows
        and the wire response so callers can recover per-leg fields
        (``instrument_key`` / ``trading_symbol``) that the
        :class:`OptionContract` dataclass does not preserve.
        """
        instrument_key = self._resolve_instrument(underlying, exchange_segment)
        body = self._client.get_chain(instrument_key, expiry)
        if not isinstance(body, dict) or body.get("status") != "success":
            logger.warning(
                "upstox_option_chain_non_success",
                extra={"underlying": underlying, "expiry": expiry, "body": body},
            )
            return [], [], body if isinstance(body, dict) else {}
        data = body.get("data")
        if not isinstance(data, list):
            return [], [], body
        contracts: list[OptionContract] = []
        for row in data:
            if isinstance(row, dict):
                contracts.append(UpstoxDomainMapper.to_option_contract(row))
        return contracts, data, body


logger = logging.getLogger(__name__)
