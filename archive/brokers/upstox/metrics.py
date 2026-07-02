"""Upstox broker metrics — backed by MetricsRegistry (parity with Dhan).

Provides counters, histograms, and gauges for:
- HTTP API request duration and count
- WebSocket message throughput
- Connection status
- Order execution metrics

Usage::

    from brokers.upstox.metrics import upstox_ws_connected, upstox_ws_reconnects

    upstox_ws_connected.set(1)
    upstox_ws_reconnects.inc()
"""

from __future__ import annotations

from infrastructure.metrics.registry import metrics_registry

# HTTP API metrics
upstox_request_total = metrics_registry.counter(
    "upstox_request_total",
    "Total HTTP requests to Upstox API",
)
upstox_request_duration_seconds = metrics_registry.histogram(
    "upstox_request_duration_seconds",
    "Upstox API request latency in seconds",
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)
upstox_request_errors_total = metrics_registry.counter(
    "upstox_request_errors_total",
    "Total Upstox API errors",
)

# WebSocket metrics
upstox_ws_messages_total = metrics_registry.counter(
    "upstox_websocket_messages_total",
    "Total Upstox WebSocket messages",
)
upstox_ws_connected = metrics_registry.gauge(
    "upstox_websocket_connected",
    "Upstox WebSocket connection status (1=connected, 0=disconnected)",
)
upstox_ws_reconnects = metrics_registry.counter(
    "upstox_websocket_reconnects_total",
    "Total Upstox WebSocket reconnection attempts",
)

# Order metrics
upstox_orders_total = metrics_registry.counter(
    "upstox_orders_total",
    "Total Upstox orders",
)
upstox_order_duration_seconds = metrics_registry.histogram(
    "upstox_order_duration_seconds",
    "Time from order placement to fill",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
)

# Portfolio metrics
upstox_portfolio_value = metrics_registry.gauge(
    "upstox_portfolio_value",
    "Current portfolio value",
)
upstox_pnl = metrics_registry.gauge(
    "upstox_pnl",
    "Current realized + unrealized P&L",
)

# Token refresh metrics
upstox_token_refresh_total = metrics_registry.counter(
    "upstox_token_refresh_total",
    "Total token refresh attempts",
)
upstox_token_refresh_errors_total = metrics_registry.counter(
    "upstox_token_refresh_errors_total",
    "Total token refresh errors",
)
