"""Instrument domain entity."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from domain.constants import DEFAULT_TICK_SIZE


@dataclass(slots=True, frozen=True)
class Instrument:
    """Canonical instrument master record — returned by broker adapters.

    This is the broker-adapter-level instrument, populated by Dhan/Upstox
    instrument loaders. Distinct from:

    * ``brokers.common.core.instruments.Instrument`` — the trading-engine
      instrument used by the strategy layer (has ``asset_class``,
      ``broker_identifier``).
    * ``brokers.dhan.domain.Instrument`` — Dhan-specific instrument with
      typed ``Exchange`` and ``InstrumentType`` enums.

    Frozen for immutability — all fields are value types.
    """

    symbol: str
    exchange: str
    security_id: str
    instrument_type: str
    lot_size: int = 1
    tick_size: Decimal = DEFAULT_TICK_SIZE
    name: str | None = None
    option_type: str | None = None
    strike_price: Decimal | None = None
    expiry: str | None = None
    underlying: str | None = None
    canonical_symbol: str | None = None
