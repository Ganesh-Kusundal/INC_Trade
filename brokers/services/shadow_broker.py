"""Shadow-run broker wrapper for safe architectural migration.

Implements the David Farley shadow-run pattern: the new service layer runs
alongside the legacy gateway in production, validating that output payloads
match before cutover.  The primary result is always returned to the caller;
the shadow is exercised purely for observability.
"""

from __future__ import annotations

import dataclasses
import logging
from typing import Any

logger = logging.getLogger(__name__)

_METHODS = (
    "place_order",
    "get_quote",
    "get_positions",
    "get_holdings",
    "get_balance",
    "get_orderbook",
)


def _to_comparable(value: Any) -> Any:
    """Convert a value to a dict-comparable form for diffing.

    Handles frozen dataclasses, plain objects with __dict__, lists, and scalars.
    """
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return dataclasses.asdict(value)  # type: ignore[arg-type]
    if isinstance(value, list):
        return [_to_comparable(item) for item in value]
    if hasattr(value, "__dict__"):
        return vars(value)
    return value


def _compute_diff(primary: Any, shadow: Any) -> list[str]:
    """Return a list of human-readable diff lines between primary and shadow results."""
    p = _to_comparable(primary)
    s = _to_comparable(shadow)

    if isinstance(p, dict) and isinstance(s, dict):
        diffs: list[str] = []
        all_keys = set(p) | set(s)
        for key in sorted(all_keys):
            pv = p.get(key, "<missing>")
            sv = s.get(key, "<missing>")
            if pv != sv:
                diffs.append(f"  key={key!r}: primary={pv!r}, shadow={sv!r}")
        return diffs

    if isinstance(p, list) and isinstance(s, list):
        if len(p) != len(s):
            return [f"  list length: primary={len(p)}, shadow={len(s)}"]
        diffs = []
        for i, (pi, si) in enumerate(zip(p, s)):
            sub = _compute_diff(pi, si)
            if sub:
                diffs.append(f"  [index={i}]")
                diffs.extend(sub)
        return diffs

    if p != s:
        return [f"  value: primary={p!r}, shadow={s!r}"]
    return []


class ShadowBroker:
    """Shadow-run wrapper for safe architectural migration.

    Routes each call to both primary (new) and shadow (legacy) paths.
    Returns the primary result unconditionally.  Logs payload diffs at WARNING
    level for validation before production cutover.

    Args:
        primary: The new broker implementation (e.g. BrokerFacade / BrokerSession).
        shadow:  The legacy gateway to run in parallel.
        enabled: Master toggle; when ``False`` the shadow is never invoked.
    """

    def __init__(self, primary: Any, shadow: Any, enabled: bool = True) -> None:
        self._primary = primary
        self._shadow = shadow
        self._enabled = enabled
        self._mismatch_count: int = 0
        self._call_count: int = 0

    # ------------------------------------------------------------------
    # Observability properties
    # ------------------------------------------------------------------

    @property
    def mismatch_count(self) -> int:
        """Total number of calls where primary and shadow results differed."""
        return self._mismatch_count

    @property
    def call_count(self) -> int:
        """Total number of shadowed method calls attempted."""
        return self._call_count

    @property
    def mismatch_rate(self) -> float:
        """Fraction of shadowed calls that produced mismatches (0.0–1.0)."""
        if self._call_count == 0:
            return 0.0
        return self._mismatch_count / self._call_count

    @property
    def enable_shadow(self) -> bool:
        """Whether shadow execution is currently enabled."""
        return self._enabled

    @enable_shadow.setter
    def enable_shadow(self, value: bool) -> None:
        self._enabled = value

    # ------------------------------------------------------------------
    # Internal shadow runner
    # ------------------------------------------------------------------

    def _run_shadow(
        self,
        method_name: str,
        primary_result: Any,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Execute the shadow call and compare its result with the primary.

        Swallows all shadow exceptions.  Increments mismatch_count on diff.
        """
        if not self._enabled:
            return

        self._call_count += 1

        shadow_method = getattr(self._shadow, method_name, None)
        if shadow_method is None:
            logger.warning(
                "ShadowBroker: shadow does not implement '%s'; skipping comparison",
                method_name,
            )
            return

        try:
            shadow_result = shadow_method(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "ShadowBroker: shadow raised exception on '%s': %s: %s",
                method_name,
                type(exc).__name__,
                exc,
            )
            return

        diffs = _compute_diff(primary_result, shadow_result)
        if diffs:
            self._mismatch_count += 1
            diff_text = "\n".join(diffs)
            logger.warning(
                "ShadowBroker: MISMATCH on '%s' (total=%d):\n%s",
                method_name,
                self._mismatch_count,
                diff_text,
            )
        else:
            logger.debug(
                "ShadowBroker: '%s' results match ✓",
                method_name,
            )

    # ------------------------------------------------------------------
    # Proxied broker methods
    # ------------------------------------------------------------------

    def place_order(self, *args: Any, **kwargs: Any) -> Any:
        """Place order via primary; shadow in parallel for comparison."""
        result = self._primary.place_order(*args, **kwargs)
        self._run_shadow("place_order", result, *args, **kwargs)
        return result

    def get_quote(self, *args: Any, **kwargs: Any) -> Any:
        """Get quote via primary; shadow in parallel for comparison."""
        result = self._primary.get_quote(*args, **kwargs)
        self._run_shadow("get_quote", result, *args, **kwargs)
        return result

    def get_positions(self, *args: Any, **kwargs: Any) -> Any:
        """Get positions via primary; shadow in parallel for comparison."""
        result = self._primary.get_positions(*args, **kwargs)
        self._run_shadow("get_positions", result, *args, **kwargs)
        return result

    def get_holdings(self, *args: Any, **kwargs: Any) -> Any:
        """Get holdings via primary; shadow in parallel for comparison."""
        result = self._primary.get_holdings(*args, **kwargs)
        self._run_shadow("get_holdings", result, *args, **kwargs)
        return result

    def get_balance(self, *args: Any, **kwargs: Any) -> Any:
        """Get balance via primary; shadow in parallel for comparison."""
        result = self._primary.get_balance(*args, **kwargs)
        self._run_shadow("get_balance", result, *args, **kwargs)
        return result

    def get_orderbook(self, *args: Any, **kwargs: Any) -> Any:
        """Get orderbook via primary; shadow in parallel for comparison."""
        result = self._primary.get_orderbook(*args, **kwargs)
        self._run_shadow("get_orderbook", result, *args, **kwargs)
        return result
