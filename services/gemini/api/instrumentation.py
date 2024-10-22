import opentelemetry.trace as trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.resources import Resource


def _instrument() -> None:
    tracer_provider = TracerProvider(
        resource=Resource.create({"service.name": "gemini"})
    )
    collector_exporter = OTLPSpanExporter()
    tracer_provider.add_span_processor(BatchSpanProcessor(collector_exporter))
    # Sampling for this trace can be configured by exposing environment variables
    # OTEL_TRACES_SAMPLER=traceidratio
    # OTEL_TRACES_SAMPLER_ARG=0.5        (for 50% sampling rate)
    trace.set_tracer_provider(tracer_provider)
