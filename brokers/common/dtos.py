"""Broker-specific DTOs that extend the canonical domain models with transport metadata.

These DTOs live in the broker layer and carry fields that are concerns of the
transport/API boundary — not the domain. Domain-level consumers (``OrderManager``,
``RiskManager``) never see these extra fields.

The OMS owns all pre-submit risk validation; broker adapters enforce their
own boundary checks without needing a ``transport_only`` policy flag.

Usage
-----
Gateways (``DhanBrokerGateway``, ``UpstoxBrokerGateway``) construct a
``BrokerOrderPayload`` from flat parameters and pass it to the broker adapter::

    from brokers.common.dtos import BrokerOrderPayload

    payload = BrokerOrderPayload(
        symbol=symbol,
        exchange=exchange,
        transaction_type=Side.BUY,
        quantity=10,
        exchange_segment=segment,
    )
    order = adapter.place_order(payload)
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from domain.requests import OrderRequest
from domain.types import ExchangeSegment


@dataclass(slots=True, frozen=True)
class BrokerOrderPayload(OrderRequest):
    """Order request with broker-transport metadata.

    Extends the canonical ``OrderRequest`` with fields that are relevant
    only at the broker-API transport layer:

    * ``exchange_segment`` — broker-specific segment enum
    * ``provider_metadata`` — broker-specific transport extensions

    Immutable by design. The ``provider_metadata`` dict is deep-copied on
    construction so mutating the caller's original dict does not affect
    the payload.
    """

    exchange_segment: ExchangeSegment = ExchangeSegment.NSE
    provider_metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Deep-copy the mutable dict to prevent aliasing bugs.
        object.__setattr__(self, "provider_metadata", deepcopy(self.provider_metadata))


__all__ = [
    "BrokerOrderPayload",
]
