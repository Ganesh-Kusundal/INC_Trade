"""Alerting engine for EventBus metrics.

This module provides a lightweight, dependency-free alerting system
that monitors :class:`EventMetrics` and fires alerts when predefined
thresholds are exceeded.

Key Features
------------
- **Threshold-Based Rules**: Define rules that fire when a metric
  exceeds a threshold (absolute count or rate per second).
- **Deduplication**: Alerts are deduplicated within a cooldown period
  to prevent alert spam.
- **Callbacks**: Custom handlers for alert delivery (logging, webhook, etc.).
- **Thread-Safe**: All operations protected by RLock.
- **Predefined Rules**: Production-ready alert rules for common scenarios.

Usage
-----
    from brokers.common.observability.alerting import (
        AlertingEngine,
        create_default_alert_rules,
    )
    from infrastructure.observability.event_metrics import EventMetrics

    metrics = EventMetrics()
    engine = AlertingEngine(metrics)

    # Register rules
    for rule in create_default_alert_rules():
        engine.register_rule(rule)

    # Evaluate rules (call periodically, e.g., every 10 seconds)
    alerts = engine.evaluate_all()
    for alert in alerts:
        print(f"[{alert.level.name}] {alert.message}")

    # Or add a custom callback
    def my_callback(alert):
        # Send to PagerDuty, Slack, etc.
        pass
    engine.add_callback(my_callback)

Alert Lifecycle
---------------
1. **Register**: Add alert rules with name, metric pattern, threshold, level.
2. **Evaluate**: Call :meth:`evaluate_all` periodically (every 10s recommended).
3. **Fire**: When threshold is exceeded, an :class:`Alert` is created.
4. **Deduplicate**: Same alert won't fire again within cooldown period.
5. **Callback**: All registered callbacks are invoked (non-blocking).
"""

from __future__ import annotations

import fnmatch
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from infrastructure.observability.event_metrics import EventMetrics

logger = logging.getLogger(__name__)


class AlertLevel(str, Enum):
    """Severity levels for alerts.

    INFO: Informational — no action required, but noteworthy.
    WARNING: Potentially concerning — should be investigated.
    CRITICAL: Immediate action required — system health at risk.
    """

    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class Alert:
    """A fired alert containing all relevant context.

    Attributes
    ----------
    level:
        Severity level of the alert.
    message:
        Human-readable description of the alert condition.
    metric_name:
        The metric that triggered the alert (e.g., "TICK/handler_error").
    threshold:
        The threshold value that was exceeded.
    current_value:
        The current metric value that triggered the alert.
    timestamp:
        Unix timestamp when the alert was fired.
    rule_name:
        Name of the rule that fired this alert.
    """

    level: AlertLevel
    message: str
    metric_name: str
    threshold: float
    current_value: float
    timestamp: float
    rule_name: str


# Type alias for alert callbacks.
AlertCallback = Callable[[Alert], None]


@dataclass
class AlertRule:
    """A rule that fires an alert when a metric exceeds a threshold.

    Attributes
    ----------
    name:
        Unique name for the rule (used for deduplication).
    metric_pattern:
        Glob pattern matching the metric name (e.g., "*/handler_error").
        Format: "event_type/outcome" (e.g., "TICK/handler_error:RuntimeError").
        Use "*" as wildcard (e.g., "*/dead_letter" matches all dead_letter outcomes).
    threshold:
        Threshold value. If the metric value exceeds this, the alert fires.
        For rate-based rules, this is events per second.
    level:
        Alert severity level.
    description:
        Human-readable description of the rule.
    callback:
        Optional callback invoked when this specific rule fires.
        In addition to rule-level callbacks, the :class:`AlertingEngine`
        has its own callback list.
    is_rate:
        If True, threshold is compared against rate (events/second)
        over the rate_window. If False, threshold is compared against
        the cumulative counter value.
    rate_window:
        Time window in seconds for rate calculation (only used if is_rate=True).
    """

    name: str
    metric_pattern: str
    threshold: float
    level: AlertLevel
    description: str
    callback: AlertCallback | None = None
    is_rate: bool = False
    rate_window: float = 60.0


class AlertingEngine:
    """Monitors EventMetrics and fires alerts when thresholds are exceeded.

    The engine is designed to be polled periodically (e.g., every 10 seconds)
    by a background thread or asyncio task. It evaluates all registered rules
    against the current metrics snapshot and fires alerts when thresholds
    are breached.

    Parameters
    ----------
    metrics:
        The EventMetrics instance to monitor.
    cooldown_seconds:
        Minimum time between firing the same alert (prevents alert spam).
        Default 300 seconds (5 minutes).

    Thread Safety
    -------------
    All public methods are protected by an RLock. Callbacks are invoked
    outside the lock to prevent blocking the metrics path.
    """

    def __init__(
        self,
        metrics: EventMetrics,
        cooldown_seconds: float = 300.0,
    ) -> None:
        self._metrics = metrics
        self._cooldown = cooldown_seconds
        self._lock = threading.RLock()
        self._rules: dict[str, AlertRule] = {}
        self._callbacks: list[AlertCallback] = []
        # Track last fire time per rule for deduplication.
        self._last_fired: dict[str, float] = {}
        # Track alerts that have been fired but not yet acknowledged.
        self._fired_alerts: list[Alert] = []

    @property
    def metrics(self) -> EventMetrics:
        """The EventMetrics instance being monitored."""
        return self._metrics

    @property
    def rule_count(self) -> int:
        """Number of registered alert rules."""
        with self._lock:
            return len(self._rules)

    @property
    def cooldown_seconds(self) -> float:
        """Cooldown period between duplicate alerts."""
        return self._cooldown

    def register_rule(self, rule: AlertRule) -> None:
        """Register an alert rule.

        If a rule with the same name already exists, it will be replaced.

        Parameters
        ----------
        rule:
            The alert rule to register.
        """
        if not rule.name:
            raise ValueError("Alert rule name cannot be empty")
        if rule.threshold < 0:
            raise ValueError("Alert rule threshold cannot be negative")

        with self._lock:
            self._rules[rule.name] = rule
            logger.info("Registered alert rule: %s", rule.name)

    def unregister_rule(self, rule_name: str) -> bool:
        """Remove a registered alert rule.

        Parameters
        ----------
        rule_name:
            Name of the rule to remove.

        Returns
        -------
        bool:
            True if the rule was found and removed, False otherwise.
        """
        with self._lock:
            if rule_name in self._rules:
                del self._rules[rule_name]
                # Also clear the last-fired time.
                self._last_fired.pop(rule_name, None)
                logger.info("Unregistered alert rule: %s", rule_name)
                return True
            return False

    def add_callback(self, callback: AlertCallback) -> None:
        """Register a callback to be invoked when any alert fires.

        Callbacks are invoked outside the engine's lock to prevent
        blocking the metrics evaluation path.

        Parameters
        ----------
        callback:
            A callable that accepts an Alert argument.
        """
        with self._lock:
            self._callbacks.append(callback)
            logger.info("Registered alert callback: %s", callback)

    def remove_callback(self, callback: AlertCallback) -> bool:
        """Remove a previously registered callback.

        Parameters
        ----------
        callback:
            The callback to remove.

        Returns
        -------
        bool:
            True if the callback was found and removed, False otherwise.
        """
        with self._lock:
            try:
                self._callbacks.remove(callback)
                return True
            except ValueError:
                return False

    def evaluate_all(self) -> list[Alert]:
        """Evaluate all registered rules against current metrics.

        This is the main evaluation method. It should be called periodically
        (e.g., every 10 seconds) by a background thread or asyncio task.

        Returns
        -------
        list[Alert]:
            List of alerts that fired during this evaluation.
            Empty list if no thresholds were exceeded.

        Thread Safety
        -------------
        Metrics are read under lock, but callbacks are invoked outside
        the lock to prevent deadlocks and blocking.
        """
        fired: list[Alert] = []
        now = time.time()

        with self._lock:
            rules_snapshot = dict(self._rules)

        for rule in rules_snapshot.values():
            alert = self._evaluate_rule(rule, now)
            if alert is not None:
                fired.append(alert)

        # Invoke callbacks outside the lock (non-blocking).
        if fired:
            self._invoke_callbacks(fired)

        return fired

    def _evaluate_rule(self, rule: AlertRule, now: float) -> Alert | None:
        """Evaluate a single rule against current metrics.

        Parameters
        ----------
        rule:
            The rule to evaluate.
        now:
            Current timestamp (for deduplication check).

        Returns
        -------
        Alert | None:
            An Alert if the threshold was exceeded and cooldown has passed,
            None otherwise.
        """
        # Check cooldown (deduplication).
        last_fire = self._last_fired.get(rule.name, 0.0)
        if (now - last_fire) < self._cooldown:
            return None

        # Find matching metrics.
        current_value = self._get_metric_value(rule)
        if current_value is None:
            return None

        # Check threshold.
        if current_value <= rule.threshold:
            return None

        # Create alert.
        alert = Alert(
            level=rule.level,
            message=self._format_alert_message(rule, current_value),
            metric_name=rule.metric_pattern,
            threshold=rule.threshold,
            current_value=current_value,
            timestamp=now,
            rule_name=rule.name,
        )

        # Update last-fired time.
        with self._lock:
            self._last_fired[rule.name] = now
            self._fired_alerts.append(alert)

        # Invoke rule-level callback (outside lock).
        if rule.callback is not None:
            try:
                rule.callback(alert)
            except Exception as exc:
                logger.exception(
                    "Alert rule callback failed for %s: %s",
                    rule.name,
                    exc,
                )

        return alert

    def _get_metric_value(self, rule: AlertRule) -> float | None:
        """Get the current value for a rule's metric pattern.

        Supports glob patterns (e.g., "*/handler_error" matches all
        event types with handler_error outcome).

        Parameters
        ----------
        rule:
            The rule containing the metric pattern.

        Returns
        -------
        float | None:
            The current metric value, or None if no match found.
        """
        snapshot = self._metrics.snapshot()
        pattern = rule.metric_pattern

        # Parse pattern: "event_type/outcome"
        if "/" not in pattern:
            # Treat as outcome-only pattern (match all event types).
            event_pattern = "*"
            outcome_pattern = pattern
        else:
            event_pattern, outcome_pattern = pattern.split("/", 1)

        total_value: float = 0.0
        found = False

        for event_type, outcomes in snapshot.items():
            if not fnmatch.fnmatch(event_type, event_pattern):
                continue
            for outcome, value in outcomes.items():
                if fnmatch.fnmatch(outcome, outcome_pattern):
                    found = True
                    if rule.is_rate:
                        # For rate rules, use the rate() method.
                        rate_value = self._metrics.rate(event_type, outcome, rule.rate_window)
                        total_value += rate_value
                    else:
                        total_value += float(value)

        return total_value if found else None

    def _format_alert_message(self, rule: AlertRule, current_value: float) -> str:
        """Format a human-readable alert message.

        Parameters
        ----------
        rule:
            The rule that fired.
        current_value:
            The current metric value.

        Returns
        -------
        str:
            Formatted alert message.
        """
        if rule.is_rate:
            return (
                f"[{rule.name}] {rule.metric_pattern} rate is "
                f"{current_value:.4f}/s (threshold: {rule.threshold:.4f}/s) — "
                f"{rule.description}"
            )
        else:
            return (
                f"[{rule.name}] {rule.metric_pattern} value is "
                f"{current_value:.0f} (threshold: {rule.threshold:.0f}) — "
                f"{rule.description}"
            )

    def _invoke_callbacks(self, alerts: list[Alert]) -> None:
        """Invoke all registered callbacks for a list of alerts.

        Callbacks are invoked outside the lock to prevent blocking.
        Exceptions in callbacks are logged but do not stop other callbacks.

        Parameters
        ----------
        alerts:
            List of alerts to pass to callbacks.
        """
        with self._lock:
            callbacks = list(self._callbacks)

        for callback in callbacks:
            for alert in alerts:
                try:
                    callback(alert)
                except Exception as exc:
                    logger.exception(
                        "Alert callback failed for %s: %s",
                        callback,
                        exc,
                    )

    def get_fired_alerts(self, limit: int = 100) -> list[Alert]:
        """Get recently fired alerts.

        Parameters
        ----------
        limit:
            Maximum number of alerts to return (most recent first).

        Returns
        -------
        list[Alert]:
            List of recently fired alerts.
        """
        with self._lock:
            return list(reversed(self._fired_alerts))[:limit]

    def clear_fired_alerts(self) -> None:
        """Clear the history of fired alerts."""
        with self._lock:
            self._fired_alerts.clear()

    def reset(self) -> None:
        """Reset the engine state (rules, callbacks, fired alerts)."""
        with self._lock:
            self._rules.clear()
            self._callbacks.clear()
            self._last_fired.clear()
            self._fired_alerts.clear()


def create_default_alert_rules() -> list[AlertRule]:
    """Create a set of production-ready default alert rules.

    These rules cover common failure scenarios that should trigger alerts
    in a production trading system.

    Returns
    -------
    list[AlertRule]:
        List of predefined alert rules ready for registration.

    Rules
    -----
    1. **High error rate**: handler_error / dispatched > 5% → CRITICAL
       Fires when the error rate exceeds 5% of dispatched events.

    2. **Dead letter queue growth**: dead_letter count > 10 in 60s → WARNING
       Fires when more than 10 events are dead-lettered in 60 seconds.

    3. **Circuit breaker open**: Any circuit breaker in OPEN state → CRITICAL
       Fires when any circuit breaker metric indicates OPEN state.

    4. **Broker fallback storm**: intelligent_gateway_fallback > 20 in 60s → WARNING
       Fires when broker fallback count exceeds 20 in 60 seconds.

    5. **Event bus backpressure**: async bus queue_size > 90% capacity → WARNING
       Fires when async bus queue is more than 90% full.

    6. **Log write failures**: log_error count > 5 → CRITICAL
       Fires when more than 5 log write errors occur.
    """
    return [
        AlertRule(
            name="high_error_rate",
            metric_pattern="*/handler_error*",
            threshold=0.05,  # 5% error rate threshold
            level=AlertLevel.CRITICAL,
            description="Handler error rate exceeds 5% of dispatched events",
            is_rate=True,
            rate_window=60.0,
        ),
        AlertRule(
            name="dead_letter_queue_growth",
            metric_pattern="*/dead_letter",
            threshold=10.0,  # More than 10 dead letters
            level=AlertLevel.WARNING,
            description="Dead letter queue growing rapidly (>10 in 60s)",
            is_rate=True,
            rate_window=60.0,
        ),
        AlertRule(
            name="circuit_breaker_open",
            metric_pattern="*/circuit_breaker:OPEN",
            threshold=0.0,  # Any occurrence is critical
            level=AlertLevel.CRITICAL,
            description="Circuit breaker is in OPEN state",
            is_rate=False,
        ),
        AlertRule(
            name="broker_fallback_storm",
            metric_pattern="*/intelligent_gateway_fallback",
            threshold=20.0,  # More than 20 fallbacks
            level=AlertLevel.WARNING,
            description="Broker fallback storm detected (>20 in 60s)",
            is_rate=True,
            rate_window=60.0,
        ),
        AlertRule(
            name="event_bus_backpressure",
            metric_pattern="*/queue_capacity_exceeded",
            threshold=0.0,  # Any occurrence indicates backpressure
            level=AlertLevel.WARNING,
            description="Event bus experiencing backpressure (>90% capacity)",
            is_rate=False,
        ),
        AlertRule(
            name="log_write_failures",
            metric_pattern="*/log_error*",
            threshold=5.0,  # More than 5 log errors
            level=AlertLevel.CRITICAL,
            description="Log write failures detected (>5)",
            is_rate=False,
        ),
    ]


__all__ = [
    "Alert",
    "AlertLevel",
    "AlertRule",
    "AlertingEngine",
    "create_default_alert_rules",
]
