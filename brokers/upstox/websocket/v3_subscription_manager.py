"""Upstox V3 WebSocket hard subscription limits.

Mirrors Trade_J ``UpstoxV3SubscriptionLimits``:

* 2 WebSocket connections per user (5 for Plus plan).
* LTPC: 5000 individual / 2000 combined
* Option Greeks: 3000 individual / 2000 combined
* Full: 2000 individual / 1500 combined
* Full D30: 50 individual / 1500 combined (Plus-only)
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from brokers.common.resilience.errors import TradeXV2Error


class SubscriptionLimitExceededError(TradeXV2Error):
    pass


@dataclass
class UpstoxV3SubscriptionLimits:
    max_connections: int = 2
    ltpc_individual: int = 5000
    ltpc_combined: int = 2000
    greeks_individual: int = 3000
    greeks_combined: int = 2000
    full_individual: int = 2000
    full_combined: int = 1500
    d30_individual: int = 50
    d30_combined: int = 1500

    @classmethod
    def for_plus_plan(cls) -> UpstoxV3SubscriptionLimits:
        return cls(max_connections=5)


class UpstoxV3SubscriptionManager:
    """Tracks per-category subscription counts and enforces limits."""

    MODES = ("ltpc", "option_greeks", "full", "full_d30")

    def __init__(self, limits: UpstoxV3SubscriptionLimits | None = None) -> None:
        self._limits = limits or UpstoxV3SubscriptionLimits()
        self._lock = threading.RLock()
        self._by_mode: dict[str, set[str]] = {m: set() for m in self.MODES}
        self._by_key: dict[str, str] = {}

    def max_connections(self) -> int:
        return self._limits.max_connections

    def total_subscriptions(self) -> int:
        with self._lock:
            return sum(len(s) for s in self._by_mode.values())

    def active_categories(self) -> list[str]:
        with self._lock:
            return [m for m in self.MODES if self._by_mode[m]]

    def ltpc_count(self) -> int:
        with self._lock:
            return len(self._by_mode["ltpc"])

    def greeks_count(self) -> int:
        with self._lock:
            return len(self._by_mode["option_greeks"])

    def full_count(self) -> int:
        with self._lock:
            return len(self._by_mode["full"])

    def d30_count(self) -> int:
        with self._lock:
            return len(self._by_mode["full_d30"])

    def mode_for(self, instrument_key: str) -> str:
        with self._lock:
            return self._by_key.get(instrument_key, "")

    def keys_for_mode(self, mode: str) -> list[str]:
        mode = self._normalise_mode(mode)
        with self._lock:
            return list(self._by_mode.get(mode, set()))

    def subscribe(self, instrument_keys: list[str], mode: str) -> None:
        mode = self._normalise_mode(mode)
        with self._lock:
            for key in instrument_keys:
                existing = self._by_key.get(key)
                if existing == mode:
                    continue
                if existing is not None:
                    self._by_mode[existing].discard(key)
                self._by_mode[mode].add(key)
                self._by_key[key] = mode
            self._enforce(mode)

    def unsubscribe(self, instrument_keys: list[str]) -> None:
        with self._lock:
            for key in instrument_keys:
                mode = self._by_key.pop(key, None)
                if mode is not None:
                    self._by_mode[mode].discard(key)

    def change_mode(self, instrument_keys: list[str], mode: str) -> None:
        self.subscribe(instrument_keys, mode)

    def _normalise_mode(self, mode: str) -> str:
        m = mode.lower().strip()
        aliases = {
            "ltp": "ltpc",
            "ltpc": "ltpc",
            "greeks": "option_greeks",
            "option_greeks": "option_greeks",
            "full_d30": "full_d30",
            "d30": "full_d30",
        }
        return aliases.get(m, m)

    def _enforce(self, mode: str) -> None:
        limits = self._limits
        sizes = {m: len(self._by_mode[m]) for m in self.MODES}
        any_active = any(sizes[m] > 0 for m in self.MODES if m != mode)
        # Per-mode individual cap
        individual_caps = {
            "ltpc": limits.ltpc_individual,
            "option_greeks": limits.greeks_individual,
            "full": limits.full_individual,
            "full_d30": limits.d30_individual,
        }
        if sizes[mode] > individual_caps[mode]:
            raise SubscriptionLimitExceededError(
                f"Upstox V3 {mode} individual subscription limit exceeded: "
                f"{sizes[mode]} > {individual_caps[mode]}"
            )
        # Combined limit applies if multiple categories are active
        if any_active:
            combined_caps = {
                "ltpc": limits.ltpc_combined,
                "option_greeks": limits.greeks_combined,
                "full": limits.full_combined,
                "full_d30": limits.d30_combined,
            }
            if sizes[mode] > combined_caps[mode]:
                raise SubscriptionLimitExceededError(
                    f"Upstox V3 {mode} combined subscription limit exceeded: "
                    f"{sizes[mode]} > {combined_caps[mode]}"
                )
