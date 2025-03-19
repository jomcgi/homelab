import discord
import opentelemetry.trace as trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.resources import Resource


def _instrument() -> None:
    tracer_provider = TracerProvider(resource=Resource.create({"service.name": "chat"}))
    collector_exporter = OTLPSpanExporter()
    tracer_provider.add_span_processor(BatchSpanProcessor(collector_exporter))
    # Sampling for this trace can be configured by exposing environment variables
    # OTEL_TRACES_SAMPLER=traceidratio
    # OTEL_TRACES_SAMPLER_ARG=0.5        (for 50% sampling rate)
    trace.set_tracer_provider(tracer_provider)


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


async def _reply_with_trace_info(message: discord.Message, response: str) -> None:
    span = trace.get_current_span()
    span_ctx = span.get_span_context()
    trace_id = trace.format_trace_id(span_ctx.trace_id)
    start = int(message.created_at.timestamp() * 1000) - 300000
    end = int(discord.utils.utcnow().timestamp() * 1000) + 300000
    dashboard_url = "https://grafana.jomcgi.dev/d/ce1n5j1xiggzkf/trace-view?orgId=1"
    trace_url = f"{dashboard_url}&var-trace_id={trace_id}&from={start}&to={end}"
    await message.reply(
        response,
        embed=discord.Embed(title="Trace Details", url=trace_url),
    )
