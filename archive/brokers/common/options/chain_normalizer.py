"""Broker-agnostic normalizers for option-chain responses.

The :class:`MarketDataGateway` contract requires ``option_chain()`` to return
a dict shaped like::

    {
        "underlying": str,
        "exchange": str,
        "expiry": str,
        "strikes": [
            {"strike": Decimal,
             "call": {"ltp", "oi", "volume", "iv", "bid", "ask",
                       "symbol", "instrument_key", "trading_symbol", ...},
             "put":  {...}}
        ]
    }

Dhan's ``extended.get_option_chain()`` already returns this shape (call/put
keys, greeks, resolved security_id/symbol). Upstox's
``UpstoxOptionsAdapter.get_option_chain()`` returns a ``list[OptionContract]``
with flat ``call_*`` / ``put_*`` fields. This module converts the Upstox
representation into the canonical strikes shape so CLI, tests, and analytics
can consume both brokers interchangeably.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from domain.entities import OptionChain, OptionContract, OptionStrike


def to_canonical_strikes(
    chain: list[OptionContract] | list[dict],
    spot: Decimal | float | int | None = None,
) -> list[dict]:
    """Convert a chain payload (Upstox or Dhan already-canonical) into the
    strike-list shape used by the gateway contract.
    """
    out: list[dict] = []
    for row in chain:
        if isinstance(row, OptionContract):
            out.append(
                {
                    "strike": row.strike,
                    "call": _leg_from_contract(row, "call"),
                    "put": _leg_from_contract(row, "put"),
                }
            )
        elif isinstance(row, dict):
            # Already-canonical Dhan-style row, pass through with normalization.
            # Dhan historically uses ``strikePrice``; canonical form is ``strike``.
            strike_val = row.get("strike") or row.get("strikePrice")
            try:
                strike = Decimal(str(strike_val)) if strike_val is not None else Decimal("0")
            except Exception:
                strike = Decimal("0")
            out.append(
                {
                    "strike": strike,
                    "call": _normalize_leg(row.get("call") or row.get("CE") or {}),
                    "put": _normalize_leg(row.get("put") or row.get("PE") or {}),
                }
            )
    return out


def _leg_from_contract(row: OptionContract, side: str) -> dict:
    return {
        "ltp": getattr(row, f"{side}_ltp"),
        "oi": getattr(row, f"{side}_oi"),
        "volume": getattr(row, f"{side}_volume"),
        "iv": getattr(row, f"{side}_iv"),
        "bid": getattr(row, f"{side}_bid"),
        "ask": getattr(row, f"{side}_ask"),
        "symbol": None,
        "trading_symbol": None,
        "instrument_key": None,
    }


def _normalize_leg(leg: Any) -> dict:
    if not isinstance(leg, dict):
        return {
            "ltp": None,
            "oi": None,
            "volume": None,
            "iv": None,
            "bid": None,
            "ask": None,
            "symbol": leg.get("symbol") if isinstance(leg, dict) else None,
            "trading_symbol": leg.get("tradingSymbol") if isinstance(leg, dict) else None,
            "instrument_key": (
                leg.get("security_id") or leg.get("instrument_key")
                if isinstance(leg, dict)
                else None
            ),
        }
    out = {
        "ltp": leg.get("ltp"),
        "oi": leg.get("oi"),
        "volume": leg.get("volume"),
        "iv": leg.get("iv"),
        "bid": leg.get("bid"),
        "ask": leg.get("ask"),
        "symbol": leg.get("symbol"),
        "trading_symbol": leg.get("trading_symbol") or leg.get("tradingSymbol"),
        "instrument_key": leg.get("instrument_key") or leg.get("security_id"),
    }
    # Pull greeks into a sub-dict if present (Dhan-style).
    greeks = leg.get("greeks")
    if isinstance(greeks, dict):
        out["greeks"] = {
            "delta": greeks.get("delta"),
            "theta": greeks.get("theta"),
            "gamma": greeks.get("gamma"),
            "vega": greeks.get("vega"),
        }
    return out


def upstox_chain_to_canonical(
    chain: list[OptionContract],
    raw_rows: list[dict] | None,
    underlying: str,
    exchange: str,
    expiry: str,
) -> OptionChain:
    """Build a canonical :class:`OptionChain` for Upstox.

    ``raw_rows`` (optional) carries the original Upstox chain payload so we
    can recover per-leg ``instrument_key`` / ``trading_symbol`` that the
    :class:`OptionContract` dataclass does not preserve. The adapter should
    pass both for full fidelity; the dataclass is used as the base.
    """
    rows = raw_rows or []
    strikes: list[OptionStrike] = []
    for idx, row in enumerate(chain):
        raw = rows[idx] if idx < len(rows) else None
        call_leg = _upstox_leg_from_raw(raw, "call_options")
        put_leg = _upstox_leg_from_raw(raw, "put_options")
        strike_dict = {
            "strike": row.strike,
            "call": {**_leg_from_contract(row, "call"), **call_leg},
            "put": {**_leg_from_contract(row, "put"), **put_leg},
        }
        strikes.append(OptionStrike.from_dict(strike_dict))
    return OptionChain(
        underlying=underlying,
        exchange=exchange,
        expiry=expiry,
        strikes=tuple(strikes),
        spot=None,
    )


def _upstox_leg_from_raw(raw: dict | None, key: str) -> dict:
    if not isinstance(raw, dict):
        return {}
    leg = raw.get(key)
    if not isinstance(leg, dict):
        return {}
    return {
        "symbol": leg.get("symbol"),
        "trading_symbol": leg.get("trading_symbol") or leg.get("tradingSymbol"),
        "instrument_key": leg.get("instrument_key") or leg.get("instrument_token"),
    }
