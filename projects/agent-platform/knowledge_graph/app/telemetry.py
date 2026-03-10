"""OpenTelemetry setup with lazy loading."""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Generator

logger = logging.getLogger(__name__)

_tracer = None


def _get_tracer():
    global _tracer
    if _tracer is None:
        from opentelemetry import trace

        _tracer = trace.get_tracer(__name__)
    return _tracer


@contextmanager
def trace_span(name: str) -> Generator:
    """Context manager for tracing spans, no-op if OTEL disabled."""
    otel_enabled = os.environ.get("OTEL_ENABLED", "true").lower() == "true"
    if otel_enabled:
        tracer = _get_tracer()
        with tracer.start_as_current_span(name) as span:
            yield span
    else:
        yield None


def setup_telemetry(service_name: str, otlp_endpoint: str = "") -> None:
    """Configure OpenTelemetry tracing."""
    otel_enabled = os.environ.get("OTEL_ENABLED", "true").lower() == "true"
    if not otel_enabled:
        logger.info("OpenTelemetry tracing is disabled")
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError as e:
        logger.warning(f"OpenTelemetry not available, tracing disabled: {e}")
        return

    resource = Resource.create(
        {"service.name": service_name, "service.version": "0.1.0"}
    )
    provider = TracerProvider(resource=resource)

    if otlp_endpoint:
        otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
        provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

    trace.set_tracer_provider(provider)
    logger.info(f"OpenTelemetry tracing configured: {otlp_endpoint}")
