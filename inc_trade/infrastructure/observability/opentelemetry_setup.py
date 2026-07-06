"""OpenTelemetry SDK integration for TradeXV2.

Sets up distributed tracing with OTLP export (Jaeger/Zipkin) or console
fallback for development. All imports are optional -- the module degrades
gracefully when OTel packages are not installed.

Usage::

    from inc_trade.infrastructure.observability.opentelemetry_setup import setup_telemetry
    setup_telemetry("tradex-api", otlp_endpoint="http://localhost:4317")
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional OTel imports -- every package is guarded so the module works even
# when none of the opentelemetry-* packages are installed.
# ---------------------------------------------------------------------------

try:
    from opentelemetry import trace as _otel_trace
    from opentelemetry.sdk.resources import SERVICE_NAME as _SERVICE_NAME
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    _HAS_SDK = True
except ImportError:
    _otel_trace = None
    TracerProvider = None
    BatchSpanProcessor = None
    Resource = None
    _SERVICE_NAME = None
    _HAS_SDK = False

try:
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

    _HAS_OTLP = True
except ImportError:
    OTLPSpanExporter = None
    _HAS_OTLP = False

try:
    from opentelemetry.sdk.trace.export import ConsoleSpanExporter

    _HAS_CONSOLE_EXPORTER = True
except ImportError:
    ConsoleSpanExporter = None
    _HAS_CONSOLE_EXPORTER = False

try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    _HAS_FASTAPI_INSTR = True
except ImportError:
    FastAPIInstrumentor = None
    _HAS_FASTAPI_INSTR = False

try:
    from opentelemetry.instrumentation.requests import RequestsInstrumentor

    _HAS_REQUESTS_INSTR = True
except ImportError:
    RequestsInstrumentor = None
    _HAS_REQUESTS_INSTR = False

try:
    from opentelemetry.propagate import set_global_textmap
    from opentelemetry.propagators.composite import CompositePropagator
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

    _HAS_PROPAGATION = True
except ImportError:
    set_global_textmap = None
    CompositePropagator = None
    TraceContextTextMapPropagator = None
    _HAS_PROPAGATION = False

# ---------------------------------------------------------------------------
# Public flag so consumers can check whether OTel is active without importing
# the SDK themselves.
# ---------------------------------------------------------------------------

otel_available: bool = False


def setup_telemetry(
    service_name: str = "tradex-api",
    otlp_endpoint: str | None = None,
    app: object | None = None,
) -> bool:
    """Initialise the OpenTelemetry tracing pipeline.

    Parameters
    ----------
    service_name:
        Logical service name exported in every span (resource attribute).
    otlp_endpoint:
        gRPC endpoint for the OTLP collector (e.g. ``http://localhost:4317``).
        When *None* or when the OTLP exporter package is missing, a
        ``ConsoleSpanExporter`` is used so development builds still get
        visible traces.
    app:
        Optional FastAPI application instance -- when provided the HTTP
        auto-instrumentor is attached immediately.

    Returns
    -------
    bool
        *True* if OTel SDK was successfully initialised; *False* if the
        required packages are missing (the callers should degrade to
        log-only tracing).
    """
    global otel_available

    if not _HAS_SDK:
        logger.info("opentelemetry-sdk not installed -- tracing will be log-only")
        return False

    # -- resource (service name) -------------------------------------------
    resource = Resource(attributes={_SERVICE_NAME: service_name})

    # -- tracer provider ---------------------------------------------------
    provider = TracerProvider(resource=resource)

    # -- span exporter -----------------------------------------------------
    if otlp_endpoint and _HAS_OTLP:
        exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
        logger.info("OTLP exporter configured -> %s", otlp_endpoint)
    elif _HAS_CONSOLE_EXPORTER:
        exporter = ConsoleSpanExporter()
        logger.info("Using ConsoleSpanExporter (dev mode)")
    else:
        logger.warning("No span exporter available -- spans will be discarded")
        exporter = None

    if exporter is not None:
        provider.add_span_processor(BatchSpanProcessor(exporter))

    # -- register as global provider ---------------------------------------
    _otel_trace.set_tracer_provider(provider)

    # -- context propagation (W3C TraceContext) ----------------------------
    if _HAS_PROPAGATION:
        set_global_textmap(CompositePropagator([TraceContextTextMapPropagator()]))
        logger.debug("W3C TraceContext propagator registered")

    # -- auto-instrumentation ----------------------------------------------
    if _HAS_FASTAPI_INSTR and app is not None:
        FastAPIInstrumentor.instrument_app(app)
        logger.info("FastAPI auto-instrumentation attached")

    if _HAS_REQUESTS_INSTR:
        RequestsInstrumentor().instrument()
        logger.info("requests library instrumented")

    otel_available = True
    logger.info("OpenTelemetry tracing initialised (service=%s)", service_name)
    return True


def get_tracer(name: str | None = None) -> object:
    """Return a ``Tracer`` from the global provider.

    If OTel is not available a no-op tracer is returned so callers never
    need to guard their own code.
    """
    if _HAS_SDK and otel_available:
        return _otel_trace.get_tracer(name or "tradex")

    # No-op fallback
    return _otel_trace


__all__ = [
    "get_tracer",
    "otel_available",
    "setup_telemetry",
]
