"""Unified metrics infrastructure for TradeXV2.

Provides a single, standardized way to collect and expose metrics.
Supports counters, gauges, histograms, and timers with Prometheus
integration.

Usage:
    from infrastructure.metrics import metrics_registry, Counter, Gauge, Histogram

    # Define metrics
    orders_counter = Counter("orders_total", "Total orders placed")
    active_positions = Gauge("active_positions", "Currently open positions")
    order_latency = Histogram("order_latency_seconds", "Order execution latency")

    # Record metrics
    orders_counter.inc()
    active_positions.set(42)
    with order_latency.time():
        place_order()
"""

from infrastructure.metrics.prometheus import PrometheusExporter
from infrastructure.metrics.registry import MetricsRegistry, metrics_registry
from infrastructure.metrics.types import (
    Counter,
    Gauge,
    Histogram,
    LabelledCounter,
    LabelledGauge,
    LabelledHistogram,
    Timer,
)

__all__ = [
    "Counter",
    "Gauge",
    "Histogram",
    "LabelledCounter",
    "LabelledGauge",
    "LabelledHistogram",
    "MetricsRegistry",
    "PrometheusExporter",
    "Timer",
    "metrics_registry",
]
