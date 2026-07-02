"""Broker auth errors shared across broker implementations."""

from __future__ import annotations

from brokers.common.resilience.errors import TradeXV2Error


class BrokerAuthError(TradeXV2Error):
    """Raised when broker authentication fails and cannot be recovered."""
