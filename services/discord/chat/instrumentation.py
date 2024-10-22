import opentelemetry.trace as trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.trace import SpanAttributes
import discord


def _instrument() -> None:
    tracer_provider = TracerProvider(resource=Resource.create({"service.name": "chat"}))
    collector_exporter = OTLPSpanExporter()
    tracer_provider.add_span_processor(BatchSpanProcessor(collector_exporter))
    # Sampling for this trace can be configured by exposing environment variables
    # OTEL_TRACES_SAMPLER=traceidratio
    # OTEL_TRACES_SAMPLER_ARG=0.5        (for 50% sampling rate)
    trace.set_tracer_provider(tracer_provider)


def _message_span(
    message: discord.Message,
) -> trace.Span:
    return trace.get_tracer(__name__).start_span(
        "discord.message",
        attributes={
            "message.id": message.id,
            "message.author.id": message.author.id,
            "message.author.name": message.author.name,
            "message.channel.id": message.channel.id,
            "message.channel.name": message.channel.name,
            "message.guild.id": message.guild.id,
            "message.guild.name": message.guild.name,
            SpanAttributes.HTTP_STATUS_CODE: 200,
        },
    )


def _add_attrs_to_span(
    span: trace.Span,
    attrs: dict[str, str],
) -> None:
    for key, value in attrs.items():
        span.set_attribute(key, value)
    return span


def _add_to_current_span(attrs: dict[str, str]) -> None:
    span = trace.get_current_span()
    _add_attrs_to_span(span, attrs)
