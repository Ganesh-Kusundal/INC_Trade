"""Tests for the 6 collapsed infrastructure protocol groups."""

from __future__ import annotations

from typing import Any

from brokers.ports.infrastructure import (
    ConcurrencyPort,
    DataAccessPort,
    HttpPort,
    ObservabilityPort,
    SecurityPort,
    WebSocketPort,
)


class TestHttpPort:
    """HttpPort protocol structural tests."""

    def test_protocol_is_runtime_checkable(self) -> None:
        assert hasattr(HttpPort, "__instancecheck__")

    def test_protocol_has_required_methods(self) -> None:
        """Verify all required methods are present in the protocol."""
        methods = ["request", "get", "post", "put", "delete"]
        for method in methods:
            assert hasattr(HttpPort, method), f"HttpPort missing {method}"


class TestWebSocketPort:
    """WebSocketPort protocol structural tests."""

    def test_protocol_is_runtime_checkable(self) -> None:
        assert hasattr(WebSocketPort, "__instancecheck__")

    def test_protocol_has_required_methods(self) -> None:
        methods = ["connect", "disconnect", "send", "receive", "subscribe", "unsubscribe"]
        for method in methods:
            assert hasattr(WebSocketPort, method), f"WebSocketPort missing {method}"

    def test_protocol_has_required_properties(self) -> None:
        assert hasattr(WebSocketPort, "is_connected")
        assert hasattr(WebSocketPort, "latency_ms")


class TestSecurityPort:
    """SecurityPort protocol structural tests."""

    def test_protocol_is_runtime_checkable(self) -> None:
        assert hasattr(SecurityPort, "__instancecheck__")

    def test_protocol_has_required_methods(self) -> None:
        methods = [
            "login",
            "logout",
            "refresh_token",
            "get_token",
            "is_authenticated",
            "get_secret",
            "store_secret",
        ]
        for method in methods:
            assert hasattr(SecurityPort, method), f"SecurityPort missing {method}"


class TestObservabilityPort:
    """ObservabilityPort protocol structural tests."""

    def test_protocol_is_runtime_checkable(self) -> None:
        assert hasattr(ObservabilityPort, "__instancecheck__")

    def test_protocol_has_required_methods(self) -> None:
        methods = [
            "counter",
            "gauge",
            "histogram",
            "start_span",
            "end_span",
            "is_healthy",
            "register_health_check",
        ]
        for method in methods:
            assert hasattr(ObservabilityPort, method), f"ObservabilityPort missing {method}"


class TestDataAccessPort:
    """DataAccessPort protocol structural tests."""

    def test_protocol_is_runtime_checkable(self) -> None:
        assert hasattr(DataAccessPort, "__instancecheck__")

    def test_protocol_has_required_methods(self) -> None:
        methods = ["get", "set", "invalidate", "clear", "has", "stats"]
        for method in methods:
            assert hasattr(DataAccessPort, method), f"DataAccessPort missing {method}"


class TestConcurrencyPort:
    """ConcurrencyPort protocol structural tests."""

    def test_protocol_is_runtime_checkable(self) -> None:
        assert hasattr(ConcurrencyPort, "__instancecheck__")

    def test_protocol_has_required_methods(self) -> None:
        methods = ["submit", "schedule", "schedule_once", "cancel", "shutdown"]
        for method in methods:
            assert hasattr(ConcurrencyPort, method), f"ConcurrencyPort missing {method}"
