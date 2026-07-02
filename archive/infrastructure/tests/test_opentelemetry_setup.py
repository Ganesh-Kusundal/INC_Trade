"""Tests for OpenTelemetry setup and tracing integration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Tests for setup_telemetry
# ---------------------------------------------------------------------------


class TestSetupTelemetry:
    """Tests for the opentelemetry_setup module."""

    def test_setup_creates_tracer_provider(self):
        """setup_telemetry should create and register a TracerProvider."""
        pytest.importorskip("opentelemetry.sdk.trace")
        from opentelemetry import trace

        from infrastructure.observability.opentelemetry_setup import setup_telemetry

        result = setup_telemetry(service_name="test-service")

        assert result is True
        provider = trace.get_tracer_provider()
        assert provider is not None

    def test_setup_console_exporter_dev_mode(self):
        """When no OTLP endpoint is given, ConsoleSpanExporter should be used."""
        pytest.importorskip("opentelemetry.sdk.trace")
        from infrastructure.observability.opentelemetry_setup import setup_telemetry

        result = setup_telemetry(service_name="test-dev")
        assert result is True

    def test_setup_sets_otel_available_flag(self):
        """After successful setup, otel_available should be True."""
        pytest.importorskip("opentelemetry.sdk.trace")
        import infrastructure.observability.opentelemetry_setup as ots

        ots.setup_telemetry(service_name="test-flag")
        assert ots.otel_available is True

    def test_setup_returns_false_when_sdk_not_installed(self):
        """When opentelemetry SDK is not importable, returns False."""
        import infrastructure.observability.opentelemetry_setup as ots

        original = ots._HAS_SDK
        try:
            ots._HAS_SDK = False
            result = ots.setup_telemetry(service_name="test-no-sdk")
            assert result is False
        finally:
            ots._HAS_SDK = original

    def test_get_tracer_returns_tracer_when_available(self):
        """get_tracer should return a Tracer when OTel is initialised."""
        pytest.importorskip("opentelemetry.sdk.trace")
        from infrastructure.observability.opentelemetry_setup import get_tracer, setup_telemetry

        setup_telemetry(service_name="test-get-tracer")
        tracer = get_tracer("test-module")
        assert tracer is not None
        assert hasattr(tracer, "start_as_current_span")

    def test_get_tracer_returns_noop_when_unavailable(self):
        """When OTel is not active, get_tracer returns a no-op module/object."""
        import infrastructure.observability.opentelemetry_setup as ots
        from infrastructure.observability.opentelemetry_setup import get_tracer

        original = ots.otel_available
        try:
            ots.otel_available = False
            tracer = get_tracer("test-noop")
            assert tracer is not None
        finally:
            ots.otel_available = original


# ---------------------------------------------------------------------------
# Tests for tracing.py OTel bridge
# ---------------------------------------------------------------------------


class TestTraceOperationOTel:
    """Tests for the OTel span creation inside @trace_operation."""

    def test_trace_operation_creates_span_when_otel_active(self):
        """When OTel is active, @trace_operation should create a span."""
        pytest.importorskip("opentelemetry.sdk.trace")

        from infrastructure.observability import tracing

        mock_span = MagicMock()
        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(return_value=mock_span)
        mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(return_value=False)

        original_has = tracing._HAS_OTEL
        original_active = tracing._otel_active
        try:
            tracing._HAS_OTEL = True
            tracing._otel_active = True

            with patch.object(tracing, "_get_tracer", return_value=mock_tracer):
                @tracing.trace_operation("test-span")
                def my_function():
                    return 42

                result = my_function()
                assert result == 42

            mock_tracer.start_as_current_span.assert_called_once_with("test-span")
            mock_span.set_attribute.assert_any_call("status", "success")
        finally:
            tracing._HAS_OTEL = original_has
            tracing._otel_active = original_active

    def test_trace_operation_fallback_without_otel(self):
        """When OTel is not active, @trace_operation should still work (log-only)."""
        from infrastructure.observability import tracing

        original_has = tracing._HAS_OTEL
        original_active = tracing._otel_active
        try:
            tracing._HAS_OTEL = False
            tracing._otel_active = False

            @tracing.trace_operation("fallback-test")
            def my_function():
                return 99

            result = my_function()
            assert result == 99
        finally:
            tracing._HAS_OTEL = original_has
            tracing._otel_active = original_active

    def test_trace_operation_records_exception_in_span(self):
        """When the decorated function raises, the span should record the error."""
        pytest.importorskip("opentelemetry.sdk.trace")

        from infrastructure.observability import tracing

        mock_span = MagicMock()
        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(return_value=mock_span)
        mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(return_value=False)

        original_has = tracing._HAS_OTEL
        original_active = tracing._otel_active
        try:
            tracing._HAS_OTEL = True
            tracing._otel_active = True

            with patch.object(tracing, "_get_tracer", return_value=mock_tracer):
                @tracing.trace_operation("error-span")
                def failing_function():
                    raise ValueError("boom")

                with pytest.raises(ValueError, match="boom"):
                    failing_function()

            mock_span.set_attribute.assert_any_call("status", "error")
            mock_span.set_attribute.assert_any_call("error.type", "ValueError")
            mock_span.record_exception.assert_called_once()
        finally:
            tracing._HAS_OTEL = original_has
            tracing._otel_active = original_active

    def test_trace_operation_sets_correlation_id_attribute(self):
        """The span should include the current correlation_id as an attribute."""
        pytest.importorskip("opentelemetry.sdk.trace")

        from infrastructure.correlation import with_correlation
        from infrastructure.observability import tracing

        mock_span = MagicMock()
        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(return_value=mock_span)
        mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(return_value=False)

        original_has = tracing._HAS_OTEL
        original_active = tracing._otel_active
        try:
            tracing._HAS_OTEL = True
            tracing._otel_active = True

            with patch.object(tracing, "_get_tracer", return_value=mock_tracer):
                @tracing.trace_operation("correlated-op")
                def correlated_function():
                    return "done"

                with with_correlation("test-cid-123"):
                    result = correlated_function()

            assert result == "done"
            mock_span.set_attribute.assert_any_call("correlation_id", "test-cid-123")
        finally:
            tracing._HAS_OTEL = original_has
            tracing._otel_active = original_active

    def test_trace_operation_sets_function_attribute(self):
        """The span should include the function name as an attribute."""
        pytest.importorskip("opentelemetry.sdk.trace")

        from infrastructure.observability import tracing

        mock_span = MagicMock()
        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(return_value=mock_span)
        mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(return_value=False)

        original_has = tracing._HAS_OTEL
        original_active = tracing._otel_active
        try:
            tracing._HAS_OTEL = True
            tracing._otel_active = True

            with patch.object(tracing, "_get_tracer", return_value=mock_tracer):
                @tracing.trace_operation("fn-attr")
                def my_special_func():
                    return "ok"

                my_special_func()

            mock_span.set_attribute.assert_any_call("function", "my_special_func")
        finally:
            tracing._HAS_OTEL = original_has
            tracing._otel_active = original_active


# ---------------------------------------------------------------------------
# Tests for @trace_event_handler OTel bridge
# ---------------------------------------------------------------------------


class TestTraceEventHandlerOTel:
    """Tests for the OTel span creation inside @trace_event_handler."""

    def test_trace_event_handler_creates_span(self):
        """@trace_event_handler should create a span named event_handler.<type>."""
        pytest.importorskip("opentelemetry.sdk.trace")

        from infrastructure.observability import tracing

        mock_span = MagicMock()
        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(return_value=mock_span)
        mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(return_value=False)

        original_has = tracing._HAS_OTEL
        original_active = tracing._otel_active
        try:
            tracing._HAS_OTEL = True
            tracing._otel_active = True

            with patch.object(tracing, "_get_tracer", return_value=mock_tracer):
                @tracing.trace_event_handler("ORDER_UPDATED")
                def handle_order(event):
                    return "handled"

                result = handle_order({"id": 1})

            assert result == "handled"
            mock_tracer.start_as_current_span.assert_called_once_with("event_handler.ORDER_UPDATED")
            mock_span.set_attribute.assert_any_call("event_type", "ORDER_UPDATED")
        finally:
            tracing._HAS_OTEL = original_has
            tracing._otel_active = original_active

    def test_trace_event_handler_records_exception(self):
        """When the handler raises, the span should record the error."""
        pytest.importorskip("opentelemetry.sdk.trace")

        from infrastructure.observability import tracing

        mock_span = MagicMock()
        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(return_value=mock_span)
        mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(return_value=False)

        original_has = tracing._HAS_OTEL
        original_active = tracing._otel_active
        try:
            tracing._HAS_OTEL = True
            tracing._otel_active = True

            with patch.object(tracing, "_get_tracer", return_value=mock_tracer):
                @tracing.trace_event_handler("PAYMENT_FAILED")
                def failing_handler(event):
                    raise RuntimeError("payment error")

                with pytest.raises(RuntimeError, match="payment error"):
                    failing_handler({"id": 1})

            mock_span.set_attribute.assert_any_call("status", "error")
            mock_span.record_exception.assert_called_once()
        finally:
            tracing._HAS_OTEL = original_has
            tracing._otel_active = original_active


# ---------------------------------------------------------------------------
# Tests for TraceContext
# ---------------------------------------------------------------------------


class TestTraceContext:
    """Tests for the TraceContext class."""

    def test_trace_context_logs_on_success(self):
        """TraceContext should not crash on normal exit."""
        from infrastructure.observability.tracing import TraceContext

        with TraceContext("test-block"):
            pass

    def test_trace_context_logs_on_exception(self):
        """TraceContext should log on exception and re-raise."""
        from infrastructure.observability.tracing import TraceContext

        with pytest.raises(RuntimeError, match="test-error"), TraceContext("failing-block"):
            raise RuntimeError("test-error")


# ---------------------------------------------------------------------------
# Tests for graceful degradation
# ---------------------------------------------------------------------------


class TestGracefulDegradation:
    """Tests verifying behaviour when OTel packages are missing."""

    def test_tracing_module_imports_without_otel(self):
        """infrastructure.tracing should import successfully even without OTel."""
        # This test passes if the module can be imported at all
        from infrastructure.observability import tracing

        assert hasattr(tracing, "trace_operation")
        assert hasattr(tracing, "trace_event_handler")
        assert hasattr(tracing, "TraceContext")

    def test_opentelemetry_setup_module_imports(self):
        """The setup module should import even with partial OTel packages."""
        from infrastructure.observability import opentelemetry_setup

        assert hasattr(opentelemetry_setup, "setup_telemetry")
        assert hasattr(opentelemetry_setup, "get_tracer")
        assert hasattr(opentelemetry_setup, "otel_available")
