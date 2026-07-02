"""Service-provider interfaces for broker integrations.

This module mirrors Trade_J's SPI concepts while staying idiomatic for Python.

.. note:: All brokers should implement ``MarketDataGateway`` from
   ``brokers.common.gateway`` directly.
"""

from __future__ import annotations

from enum import Enum


class BrokerSource(str, Enum):
    """Broker provider identity."""

    DHAN = "dhan"
    ICICI = "icici"
    UPSTOX = "upstox"
    PAPER = "paper"
    BINANCE = "binance"
