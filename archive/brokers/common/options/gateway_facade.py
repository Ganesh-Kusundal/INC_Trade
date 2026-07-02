"""Broker-agnostic options facade — exposes a uniform
``get_expiries`` / ``get_option_chain`` interface on every gateway.

Both Dhan and Upstox gateways now expose ``self.options`` returning an
instance of this facade wrapping the broker's native options adapter.
The facade normalizes exchange-segment strings and returns the canonical
:class:`~domain.entities.OptionChain` shape.
"""

from __future__ import annotations

from typing import Any

from domain.entities import OptionChain


class GatewayOptionsFacade:
    """Thin wrapper around a broker's native options adapter."""

    def __init__(self, adapter: Any, exchange_normalize=None) -> None:
        self._adapter = adapter
        self._normalize = exchange_normalize

    def get_expiries(self, underlying: str, exchange: str = "NFO") -> list[str]:
        exchange = self._normalize_exchange(underlying, exchange)
        try:
            return list(self._adapter.get_expiries(underlying, exchange))
        except RuntimeError:
            # Underlying not in instrument master — return empty list so
            # CLI/validate commands degrade gracefully instead of crashing.
            return []

    def get_option_chain(
        self, underlying: str, exchange: str = "NFO", expiry: str | None = None
    ) -> OptionChain:
        from brokers.common.options.chain_normalizer import to_canonical_strikes

        exchange = self._normalize_exchange(underlying, exchange)
        if expiry is None:
            expiries = self.get_expiries(underlying, exchange)
            if not expiries:
                return OptionChain(underlying=underlying, exchange=exchange, expiry="")
            expiry = expiries[0]
        if hasattr(self._adapter, "get_option_chain_with_meta"):
            contracts, raw_rows, _body = self._adapter.get_option_chain_with_meta(
                underlying, exchange, expiry
            )
            return _upstox_canonical(contracts, raw_rows, underlying, exchange, expiry)
        chain = self._adapter.get_option_chain(underlying, exchange, expiry)
        if isinstance(chain, OptionChain):
            return chain
        if isinstance(chain, dict):
            strikes = to_canonical_strikes(chain.get("strikes", []))
            return OptionChain.from_dict(
                {
                    "underlying": chain.get("underlying", underlying),
                    "exchange": chain.get("exchange", exchange),
                    "expiry": chain.get("expiry", expiry),
                    "spot": chain.get("spot"),
                    "strikes": strikes,
                }
            )
        return OptionChain.from_dict(
            {
                "underlying": underlying,
                "exchange": exchange,
                "expiry": expiry,
                "strikes": to_canonical_strikes(chain),
            }
        )

    def _normalize_exchange(self, underlying: str, exchange: str) -> str:
        if self._normalize is None:
            return exchange
        try:
            return self._normalize(underlying, exchange)
        except Exception:
            return exchange


def _upstox_canonical(contracts, raw_rows, underlying, exchange, expiry) -> OptionChain:
    from brokers.common.options.chain_normalizer import upstox_chain_to_canonical

    return upstox_chain_to_canonical(contracts, raw_rows, underlying, exchange, expiry)
