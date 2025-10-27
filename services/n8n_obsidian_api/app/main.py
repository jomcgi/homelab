"""Main FastAPI application with OpenTelemetry tracing."""

import logging

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from services.n8n_obsidian_api.app.config import settings
from services.n8n_obsidian_api.app.routers import notes


class HealthCheckFilter(logging.Filter):
    """Filter out health check logs from uvicorn access logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Return False to exclude health check endpoint logs."""
        return record.getMessage().find("/ready") == -1


# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Filter out health check logs from uvicorn access logger
logging.getLogger("uvicorn.access").addFilter(HealthCheckFilter())


def setup_telemetry():
    """Configure OpenTelemetry tracing."""
    if not settings.otel_enabled:
        logger.info("OpenTelemetry tracing is disabled")
        return

    if not settings.otel_exporter_otlp_endpoint:
        logger.warning("OpenTelemetry is enabled but no OTLP endpoint configured, using default")

    # Create a resource identifying this service
    resource = Resource.create(
        {
            "service.name": settings.otel_service_name,
            "service.version": "0.1.0",
        }
    )

    # Set up the tracer provider
    provider = TracerProvider(resource=resource)

    # Configure OTLP exporter
    if settings.otel_exporter_otlp_endpoint:
        otlp_exporter = OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint)
        provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

    # Set as global tracer provider
    trace.set_tracer_provider(provider)

    logger.info(
        f"OpenTelemetry tracing configured with endpoint: {settings.otel_exporter_otlp_endpoint}"
    )


# Initialize telemetry before creating the app
setup_telemetry()

# Create FastAPI application
app = FastAPI(
    title="n8n Obsidian API",
    description=(
        "Type-safe FastAPI service providing restricted access to Obsidian API for n8n workflows. "
        "Write operations are restricted to /n8n/ folder, read operations allowed vault-wide."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Include routers
app.include_router(notes.router)


@app.get("/", tags=["health"])
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "n8n-obsidian-api",
        "version": "0.1.0",
    }


@app.get("/ready", tags=["health"])
async def readiness_check():
    """Readiness check endpoint for Kubernetes."""
    return {
        "status": "ready",
        "service": "n8n-obsidian-api",
    }


# Instrument FastAPI app with OpenTelemetry
if settings.otel_enabled:
    FastAPIInstrumentor.instrument_app(app)
    HTTPXClientInstrumentor().instrument()
    logger.info("FastAPI and HTTPX instrumented with OpenTelemetry")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.service_host,
        port=settings.service_port,
        log_level=settings.log_level.lower(),
    )
