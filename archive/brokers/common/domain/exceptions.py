"""Canonical exception hierarchy for the TradeXV2 platform.

This module defines the root exception and all platform-level (non-broker)
exceptions.  Broker-specific exceptions live in
``brokers.common.resilience.errors`` and inherit from :class:`TradeXV2Error`.

Why this module exists
----------------------
The root exception previously lived in ``brokers.common.resilience.errors``,
which forced infrastructure, application, and even domain code to depend on
a *broker* module for basic error handling.  That violated the clean-
architecture dependency rule (inner layers must not depend on outer layers).

By placing the root in ``domain.exceptions``, every layer can catch or raise
platform errors without reaching into broker territory.
"""

from __future__ import annotations


class TradeXV2Error(Exception):
    """Root exception for all TradeXV2 errors."""


class DataError(TradeXV2Error):
    """Base exception for datalake and data processing errors."""


class ConfigError(TradeXV2Error):
    """Configuration error (missing or invalid settings)."""


class ValidationError(TradeXV2Error):
    """Input validation error."""


__all__ = [
    "ConfigError",
    "DataError",
    "TradeXV2Error",
    "ValidationError",
]
