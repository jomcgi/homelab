from enum import Enum
import logging
import structlog
from structlog.types import EventDict, WrappedLogger
import opentelemetry.trace as trace


class _LogEventFields(Enum):
    """Enumeration of fields that are added to log events."""

    SPAN_ID = "spanId"
    TRACE = "trace"


def otel_span_processor(
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


def configure_structlog():
    logging.basicConfig(level=logging.INFO)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            otel_span_processor,
            structlog.processors.TimeStamper(),
            structlog.processors.CallsiteParameterAdder(),
            structlog.processors.UnicodeDecoder(),
            structlog.processors.add_log_level,
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ]
    )
