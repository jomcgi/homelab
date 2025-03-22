import opentelemetry.trace as trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.resources import Resource
from enum import Enum
import logging
import structlog
from structlog.types import EventDict, WrappedLogger
import os


class _LogEventFields(Enum):
    """Enumeration of fields that are added to log events."""

    SPAN_ID = "spanId"
    TRACE = "trace"


def _otel_span_processor(
    wrapped_logger: WrappedLogger,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    try:
        span_ctx = trace.get_current_span().get_span_context()
        if not span_ctx.is_valid:
            return event_dict
        event_dict.update(
            {
                _LogEventFields.SPAN_ID.value: trace.format_span_id(span_ctx.span_id),
                _LogEventFields.TRACE.value: trace.format_trace_id(span_ctx.trace_id),
            }
        )
    except Exception:  # pylint: disable=broad-except
        # Catch all exceptions to ensure that this function does not crash the application
        pass
    return event_dict


def _configure_structlog():
    logging.basicConfig(level=logging.INFO)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _otel_span_processor,
            structlog.processors.TimeStamper(),
            structlog.processors.CallsiteParameterAdder(),
            structlog.processors.UnicodeDecoder(),
            structlog.processors.add_log_level,
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ]
    )


def _instrument() -> None:
    tracer_provider = TracerProvider(resource=Resource.create())
    if os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", None) is not None:
        collector_exporter = OTLPSpanExporter()
        tracer_provider.add_span_processor(BatchSpanProcessor(collector_exporter))
    # Sampling for this trace can be configured by exposing environment variables
    # OTEL_TRACES_SAMPLER=traceidratio
    # OTEL_TRACES_SAMPLER_ARG=0.5        (for 50% sampling rate)
    trace.set_tracer_provider(tracer_provider)
