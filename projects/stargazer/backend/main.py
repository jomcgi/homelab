"""Stargazer pipeline entry point with OpenTelemetry tracing."""

import asyncio
import logging
import os
import sys
from contextlib import contextmanager
from typing import Generator

import httpx

from projects.stargazer.backend import acquisition, preprocessing, spatial, weather
from projects.stargazer.backend.config import Settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Lazy-load OpenTelemetry to avoid import errors when OTEL is disabled
# (grpc has native extensions that may not be available in all environments)
_tracer = None


def _get_tracer():
    """Get the tracer, initializing OTEL if needed."""
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


def setup_telemetry(settings: Settings) -> None:
    """Configure OpenTelemetry tracing."""
    if not settings.otel_enabled:
        logger.info("OpenTelemetry tracing is disabled")
        return

    # Lazy-import OTEL dependencies (may not be available in all environments)
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

    if not settings.otel_exporter_otlp_endpoint:
        logger.warning("OpenTelemetry is enabled but no OTLP endpoint configured")

    # Create a resource identifying this service
    resource = Resource.create(
        {
            "service.name": settings.otel_service_name,
            "service.version": "0.1.0",
        }
    )

    # Set up the tracer provider
    provider = TracerProvider(resource=resource)

    # Configure OTLP exporter if endpoint is set
    if settings.otel_exporter_otlp_endpoint:
        otlp_exporter = OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint)
        provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

    # Set as global tracer provider
    trace.set_tracer_provider(provider)

    logger.info(
        f"OpenTelemetry tracing configured: {settings.otel_exporter_otlp_endpoint}"
    )


def ensure_directories(settings: Settings) -> None:
    """Create data directories if they don't exist."""
    for directory in [
        settings.raw_dir,
        settings.processed_dir,
        settings.cache_dir,
        settings.output_dir,
    ]:
        directory.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Ensured directory exists: {directory}")


async def run_pipeline(settings: Settings) -> None:
    """
    Execute the full data pipeline.

    Phase 1: Data Acquisition (parallel downloads)
    Phase 2: Preprocessing (GDAL/raster operations)
    Phase 3: Spatial Analysis (geopandas/shapely)
    Phase 4: Weather Integration (MET Norway API + scoring)
    """
    with trace_span("stargazer.pipeline") as span:
        if span:
            span.set_attribute("data_dir", str(settings.data_dir))
            span.set_attribute("grid_spacing_m", settings.grid_spacing_m)
            span.set_attribute("forecast_hours", settings.forecast_hours)

        # Phase 1: Data Acquisition (parallel)
        with trace_span("phase1.acquisition"):
            logger.info("Phase 1: Data Acquisition")
            async with httpx.AsyncClient(timeout=300, follow_redirects=True) as client:
                await asyncio.gather(
                    acquisition.download_lp_atlas(settings, client),
                    acquisition.download_colorbar(settings, client),
                    acquisition.download_osm_roads(settings, client),
                )
            await acquisition.download_dem(settings)
            logger.info("Phase 1 complete")

        # Phase 2: Preprocessing
        with trace_span("phase2.preprocessing"):
            logger.info("Phase 2: Preprocessing")
            preprocessing.georeference_raster(settings)
            preprocessing.extract_palette(settings)
            preprocessing.extract_roads(settings)
            preprocessing.clip_dem(settings)
            logger.info("Phase 2 complete")

        # Phase 3: Spatial Analysis
        with trace_span("phase3.spatial_analysis"):
            logger.info("Phase 3: Spatial Analysis")
            spatial.extract_dark_regions(settings)
            spatial.buffer_roads(settings)
            spatial.intersect_dark_accessible(settings)
            spatial.generate_sample_grid(settings)
            spatial.enrich_points(settings)
            logger.info("Phase 3 complete")

        # Phase 4: Weather Integration
        with trace_span("phase4.weather_integration"):
            logger.info("Phase 4: Weather Integration")
            await weather.fetch_all_forecasts(settings)
            weather.score_locations(settings)
            weather.output_best_locations(settings)
            logger.info("Phase 4 complete")

        logger.info("Pipeline complete!")


def main() -> int:
    """Main entry point for the stargazer pipeline."""
    logger.info("Starting Stargazer - Dark Sky Location Finder")

    try:
        settings = Settings()  # type: ignore[call-arg]
    except Exception as e:
        logger.exception(f"Failed to load configuration: {e}")
        return 1

    setup_telemetry(settings)
    ensure_directories(settings)

    try:
        asyncio.run(run_pipeline(settings))
        return 0
    except Exception as e:
        logger.exception(f"Pipeline failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
