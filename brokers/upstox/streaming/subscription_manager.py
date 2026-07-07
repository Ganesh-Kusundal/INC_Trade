"""Upstox V3 subscription manager — enforces per-plan subscription limits.

Tracks active subscriptions and enforces limits based on plan tier:
- Standard plan: 25 instruments total
- Plus plan: 50+ instruments

Individual mode caps:
- ltpc: 5000 (individual), 2000 (combined with other modes)
- full: 2000 (individual)
- option_greeks: 5000 (individual)
- full_d30: 20 (individual)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from brokers.infrastructure.logging import get_logger

logger = get_logger(__name__)


class PlanTier(str, Enum):
    """Upstox subscription plan tier."""
    STANDARD = "standard"
    PLUS = "plus"


@dataclass(frozen=True, slots=True)
class SubscriptionLimits:
    """Subscription limits for a plan tier."""
    total_instruments: int = 25
    ltpc_individual: int = 5000
    ltpc_combined: int = 2000
    full_individual: int = 2000
    option_greeks_individual: int = 5000
    full_d30_individual: int = 20


# Default limits per tier
_TIER_LIMITS: dict[PlanTier, SubscriptionLimits] = {
    PlanTier.STANDARD: SubscriptionLimits(
        total_instruments=25,
        ltpc_individual=5000,
        ltpc_combined=2000,
        full_individual=2000,
        option_greeks_individual=5000,
        full_d30_individual=20,
    ),
    PlanTier.PLUS: SubscriptionLimits(
        total_instruments=50,
        ltpc_individual=5000,
        ltpc_combined=2000,
        full_individual=2000,
        option_greeks_individual=5000,
        full_d30_individual=20,
    ),
}


class SubscriptionLimitExceededError(Exception):
    """Raised when subscription limits are exceeded."""


class UpstoxV3SubscriptionManager:
    """Tracks and enforces subscription limits for Upstox V3 WebSocket.

    Usage::

        manager = UpstoxV3SubscriptionManager(tier=PlanTier.STANDARD)
        manager.subscribe(["NSE_EQ|INE002A01018", "NSE_EQ|INE012A01024"], mode="ltpc")
        print(manager.active_count)  # 2
        manager.unsubscribe(["NSE_EQ|INE002A01018"])
    """

    def __init__(self, tier: PlanTier = PlanTier.STANDARD) -> None:
        self._tier = tier
        self._limits = _TIER_LIMITS[tier]
        self._subscriptions: dict[str, str] = {}  # instrument_key -> mode
        self._mode_counts: dict[str, int] = {}    # mode -> count

    @property
    def tier(self) -> PlanTier:
        return self._tier

    @property
    def limits(self) -> SubscriptionLimits:
        return self._limits

    @property
    def active_count(self) -> int:
        return len(self._subscriptions)

    @property
    def active_instruments(self) -> set[str]:
        return set(self._subscriptions.keys())

    def subscribe(self, instruments: list[str], mode: str = "ltpc") -> None:
        """Subscribe to instruments with the given mode.

        Raises SubscriptionLimitExceededError if limits would be exceeded.
        """
        mode = _normalize_mode(mode)

        # Check total limit
        new_count = len(set(instruments) - set(self._subscriptions.keys()))
        if self.active_count + new_count > self._limits.total_instruments:
            raise SubscriptionLimitExceededError(
                f"Would exceed total limit ({self._limits.total_instruments}): "
                f"current={self.active_count}, adding={new_count}"
            )

        # Check mode-specific limit
        mode_limit = self._get_mode_limit(mode)
        current_mode_count = self._mode_counts.get(mode, 0)
        if current_mode_count + new_count > mode_limit:
            raise SubscriptionLimitExceededError(
                f"Would exceed {mode} limit ({mode_limit}): "
                f"current={current_mode_count}, adding={new_count}"
            )

        # Apply subscriptions — handle mode changes for already-subscribed instruments
        for inst in instruments:
            old_mode = self._subscriptions.get(inst)
            if old_mode is not None and old_mode != mode:
                # Mode switch — decrement old, increment new
                self._mode_counts[old_mode] = max(0, self._mode_counts.get(old_mode, 0) - 1)
                self._mode_counts[mode] = self._mode_counts.get(mode, 0) + 1
            elif old_mode is None:
                # New subscription — increment new mode count
                self._mode_counts[mode] = self._mode_counts.get(mode, 0) + 1
            # If old_mode == mode, no count change needed
            self._subscriptions[inst] = mode

        logger.debug(
            "upstox_subscribed",
            count=len(instruments),
            mode=mode,
            total=self.active_count,
        )

    def unsubscribe(self, instruments: list[str]) -> None:
        """Unsubscribe from instruments."""
        for inst in instruments:
            mode = self._subscriptions.pop(inst, None)
            if mode is not None:
                self._mode_counts[mode] = max(0, self._mode_counts.get(mode, 0) - 1)

    def get_mode(self, instrument: str) -> str | None:
        """Get the current mode for an instrument, or None if not subscribed."""
        return self._subscriptions.get(instrument)

    def get_instruments_by_mode(self, mode: str) -> list[str]:
        """Get all instruments subscribed with the given mode."""
        mode = _normalize_mode(mode)
        return [k for k, v in self._subscriptions.items() if v == mode]

    def clear(self) -> None:
        """Remove all subscriptions."""
        self._subscriptions.clear()
        self._mode_counts.clear()

    def _get_mode_limit(self, mode: str) -> int:
        """Get the subscription limit for a mode, considering combined caps."""
        has_full = self._mode_counts.get("full", 0) > 0
        has_greeks = self._mode_counts.get("option_greeks", 0) > 0

        if mode == "ltpc":
            if has_full or has_greeks:
                return self._limits.ltpc_combined
            return self._limits.ltpc_individual
        if mode == "full":
            return self._limits.full_individual
        if mode == "option_greeks":
            return self._limits.option_greeks_individual
        if mode == "full_d30":
            return self._limits.full_d30_individual
        return self._limits.total_instruments


def _normalize_mode(mode: str) -> str:
    """Normalize mode strings."""
    mode = mode.lower().strip()
    if mode in ("ltp", "ltpc"):
        return "ltpc"
    if mode in ("quote", "full"):
        return "full"
    if mode in ("option_greeks", "greeks"):
        return "option_greeks"
    if mode in ("full_d30", "d30", "depth"):
        return "full_d30"
    return "ltpc"


__all__ = [
    "PlanTier",
    "SubscriptionLimits",
    "SubscriptionLimitExceededError",
    "UpstoxV3SubscriptionManager",
]
