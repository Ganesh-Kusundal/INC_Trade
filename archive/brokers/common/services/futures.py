"""Shared future-chain building helper (REF-04 extraction).

Both Dhan and Upstox gateways had nearly identical ``future_chain()``
implementations.  This module consolidates the shared pipeline so each
gateway delegates to ``build_future_chain()``.
"""

from __future__ import annotations

from typing import Any

from domain import FutureChain


def build_future_chain(
    futures_provider: Any,
    underlying: str,
    exchange: str,
) -> FutureChain:
    """Build a ``FutureChain`` from a ``FuturesProvider``-compatible adapter.

    Parameters
    ----------
    futures_provider
        Any object with ``get_contracts(underlying, segment)`` and
        ``get_expiries(underlying, segment)`` methods.
    underlying
        Underlying symbol (e.g. "NIFTY", "RELIANCE").
    exchange
        Exchange identifier; remapped via ``INDEX_TO_FNO_EXCHANGE``
        when *underlying* is a known index.
    """
    from config.indices import INDEX_TO_FNO_EXCHANGE

    segment = INDEX_TO_FNO_EXCHANGE.get(underlying.upper(), exchange)
    contracts = futures_provider.get_contracts(underlying, segment)
    expiries = futures_provider.get_expiries(underlying, segment)
    chain = []
    for c in contracts:
        if not isinstance(c, dict):
            continue
        chain.append(
            {
                "expiry": c.get("expiry", ""),
                "symbol": c.get("symbol", c.get("trading_symbol", "")),
                "lot_size": c.get("lot_size", 1),
                "underlying": c.get("underlying", underlying),
            }
        )
    return FutureChain.from_dict(
        {
            "underlying": underlying,
            "exchange": segment,
            "expiries": expiries,
            "contracts": chain,
        }
    )
