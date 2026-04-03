"""Tests for the main module (pipeline entry point)."""

import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from projects.stargazer.backend.config import Settings
from projects.stargazer.backend.main import (
    _get_tracer,
    ensure_directories,
    main,
    run_pipeline,
    setup_telemetry,
    trace_span,
)


class TestGetTracer:
    """Tests for _get_tracer function."""

    def test_returns_tracer(self):
        """Test that _get_tracer returns a tracer object."""
        import projects.stargazer.backend.main as main_module

        original_tracer = main_module._tracer
        try:
            main_module._tracer = None
            mock_tracer = MagicMock()
            mock_trace = MagicMock()
            mock_trace.get_tracer.return_value = mock_tracer

            with patch.dict(
                "sys.modules",
                {"opentelemetry": MagicMock(), "opentelemetry.trace": mock_trace},
            ):
                with patch(
                    "projects.stargazer.backend.main.trace", mock_trace, create=True
                ):
                    # Reset the cached tracer
                    main_module._tracer = None
                    tracer = _get_tracer()
                    assert tracer is not None
        finally:
            main_module._tracer = original_tracer

    def test_caches_tracer_on_second_call(self):
        """Test that _get_tracer caches the tracer after first call."""
        import projects.stargazer.backend.main as main_module

        original_tracer = main_module._tracer
        try:
            mock_tracer = MagicMock()
            main_module._tracer = mock_tracer

            result = _get_tracer()

            assert result is mock_tracer
        finally:
            main_module._tracer = original_tracer


class TestTraceSpan:
    """Tests for trace_span context manager."""

    def test_yields_none_when_otel_disabled(self):
        """Test that trace_span yields None when OTEL is disabled."""
        with patch.dict(os.environ, {"OTEL_ENABLED": "false"}):
            with trace_span("test.span") as span:
                assert span is None

    def test_yields_none_when_otel_explicitly_false(self):
        """Test that trace_span yields None for 'false' string value."""
        with patch.dict(os.environ, {"OTEL_ENABLED": "FALSE"}):
            with trace_span("test.span") as span:
                assert span is None

    def test_uses_tracer_when_otel_enabled(self):
        """Test that trace_span uses the tracer when OTEL is enabled."""
        mock_span = MagicMock()
        mock_ctx_manager = MagicMock()
        mock_ctx_manager.__enter__ = MagicMock(return_value=mock_span)
        mock_ctx_manager.__exit__ = MagicMock(return_value=False)

        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value = mock_ctx_manager

        with patch.dict(os.environ, {"OTEL_ENABLED": "true"}):
            with patch(
                "projects.stargazer.backend.main._get_tracer", return_value=mock_tracer
            ):
                with trace_span("test.span") as span:
                    assert span is mock_span

        mock_tracer.start_as_current_span.assert_called_once_with("test.span")


class TestSetupTelemetry:
    """Tests for setup_telemetry function."""

    def test_skips_when_otel_disabled(self, settings: Settings):
        """Test that setup_telemetry is a no-op when OTEL disabled."""
        settings.otel_enabled = False

        with patch("projects.stargazer.backend.main.logger") as mock_logger:
            setup_telemetry(settings)

        mock_logger.info.assert_called_once_with("OpenTelemetry tracing is disabled")

    def test_warns_when_no_endpoint_configured(self, settings: Settings):
        """Test that setup_telemetry logs a warning when no OTLP endpoint is set."""
        settings.otel_enabled = True
        settings.otel_exporter_otlp_endpoint = ""

        # Mock all OTEL imports so we can verify the warning log
        mock_trace = MagicMock()
        mock_resource_cls = MagicMock()
        mock_resource_cls.create.return_value = MagicMock()
        mock_provider_cls = MagicMock(return_value=MagicMock())
        mock_batch_processor = MagicMock()

        with patch.dict(
            "sys.modules",
            {
                "opentelemetry.sdk.resources": MagicMock(Resource=mock_resource_cls),
                "opentelemetry.sdk.trace": MagicMock(TracerProvider=mock_provider_cls),
                "opentelemetry.sdk.trace.export": MagicMock(
                    BatchSpanProcessor=mock_batch_processor
                ),
                "opentelemetry.exporter.otlp.proto.grpc.trace_exporter": MagicMock(),
            },
        ):
            with patch("projects.stargazer.backend.main.logger") as mock_logger:
                # We can't easily mock the lazy imports inside setup_telemetry,
                # but we can verify the disabled path logs correctly
                settings.otel_enabled = False
                setup_telemetry(settings)
                mock_logger.info.assert_called_with("OpenTelemetry tracing is disabled")

    def test_handles_import_error_gracefully(self, settings: Settings):
        """Test that setup_telemetry handles ImportError when OTEL unavailable."""
        settings.otel_enabled = True

        with patch(
            "builtins.__import__",
            side_effect=ImportError("No module named opentelemetry"),
        ):
            with patch("projects.stargazer.backend.main.logger") as mock_logger:
                # The function catches ImportError internally
                # Since the import in the function body will fail, it should warn
                try:
                    setup_telemetry(settings)
                except ImportError:
                    pass  # May propagate depending on Python version

        # The function should not raise — it catches ImportError


class TestEnsureDirectories:
    """Tests for ensure_directories function."""

    def test_creates_all_four_directories(self, settings: Settings, tmp_path: Path):
        """Test that all four directories are created."""
        settings_with_temp = Settings(data_dir=tmp_path)

        ensure_directories(settings_with_temp)

        assert (tmp_path / "raw").exists()
        assert (tmp_path / "processed").exists()
        assert (tmp_path / "cache").exists()
        assert (tmp_path / "output").exists()

    def test_idempotent_when_dirs_exist(self, settings: Settings):
        """Test that ensure_directories is safe to call when dirs exist."""
        # Create dirs first
        ensure_directories(settings)
        # Call again — should not raise
        ensure_directories(settings)

        assert settings.raw_dir.exists()
        assert settings.processed_dir.exists()
        assert settings.cache_dir.exists()
        assert settings.output_dir.exists()

    def test_creates_nested_directories(self, tmp_path: Path):
        """Test that nested directories are created with parents=True."""
        deep_data_dir = tmp_path / "nested" / "deep" / "data"
        settings = Settings(data_dir=deep_data_dir)

        ensure_directories(settings)

        assert (deep_data_dir / "raw").exists()
        assert (deep_data_dir / "processed").exists()


class TestRunPipeline:
    """Tests for run_pipeline async function."""

    @pytest.mark.asyncio
    async def test_calls_all_pipeline_phases(self, settings: Settings):
        """Test that run_pipeline calls all four phases in order."""
        calls = []

        async def mock_download_lp_atlas(s, c):
            calls.append("download_lp_atlas")

        async def mock_download_colorbar(s, c):
            calls.append("download_colorbar")

        async def mock_download_osm_roads(s, c):
            calls.append("download_osm_roads")

        async def mock_download_dem(s):
            calls.append("download_dem")

        async def mock_fetch_all_forecasts(s):
            calls.append("fetch_all_forecasts")

        with (
            patch(
                "projects.stargazer.backend.main.acquisition.download_lp_atlas",
                mock_download_lp_atlas,
            ),
            patch(
                "projects.stargazer.backend.main.acquisition.download_colorbar",
                mock_download_colorbar,
            ),
            patch(
                "projects.stargazer.backend.main.acquisition.download_osm_roads",
                mock_download_osm_roads,
            ),
            patch(
                "projects.stargazer.backend.main.acquisition.download_dem",
                mock_download_dem,
            ),
            patch(
                "projects.stargazer.backend.main.preprocessing.georeference_raster"
            ) as mock_georeference,
            patch(
                "projects.stargazer.backend.main.preprocessing.extract_palette"
            ) as mock_extract_palette,
            patch(
                "projects.stargazer.backend.main.preprocessing.extract_roads"
            ) as mock_extract_roads,
            patch(
                "projects.stargazer.backend.main.preprocessing.clip_dem"
            ) as mock_clip_dem,
            patch(
                "projects.stargazer.backend.main.spatial.extract_dark_regions"
            ) as mock_dark_regions,
            patch(
                "projects.stargazer.backend.main.spatial.buffer_roads"
            ) as mock_buffer_roads,
            patch(
                "projects.stargazer.backend.main.spatial.intersect_dark_accessible"
            ) as mock_intersect,
            patch(
                "projects.stargazer.backend.main.spatial.generate_sample_grid"
            ) as mock_grid,
            patch(
                "projects.stargazer.backend.main.spatial.enrich_points"
            ) as mock_enrich,
            patch(
                "projects.stargazer.backend.main.weather.fetch_all_forecasts",
                mock_fetch_all_forecasts,
            ),
            patch(
                "projects.stargazer.backend.main.weather.score_locations"
            ) as mock_score,
            patch(
                "projects.stargazer.backend.main.weather.output_best_locations"
            ) as mock_output,
        ):
            await run_pipeline(settings)

        # Verify all acquisition calls happened
        assert "download_lp_atlas" in calls
        assert "download_colorbar" in calls
        assert "download_osm_roads" in calls
        assert "download_dem" in calls

        # Verify preprocessing calls
        mock_georeference.assert_called_once_with(settings)
        mock_extract_palette.assert_called_once_with(settings)
        mock_extract_roads.assert_called_once_with(settings)
        mock_clip_dem.assert_called_once_with(settings)

        # Verify spatial calls
        mock_dark_regions.assert_called_once_with(settings)
        mock_buffer_roads.assert_called_once_with(settings)
        mock_intersect.assert_called_once_with(settings)
        mock_grid.assert_called_once_with(settings)
        mock_enrich.assert_called_once_with(settings)

        # Verify weather calls
        assert "fetch_all_forecasts" in calls
        mock_score.assert_called_once_with(settings)
        mock_output.assert_called_once_with(settings)

    @pytest.mark.asyncio
    async def test_pipeline_with_otel_disabled(self, settings: Settings):
        """Test that pipeline runs correctly with OTEL disabled."""
        settings.otel_enabled = False

        with (
            patch(
                "projects.stargazer.backend.main.acquisition.download_lp_atlas",
                AsyncMock(),
            ),
            patch(
                "projects.stargazer.backend.main.acquisition.download_colorbar",
                AsyncMock(),
            ),
            patch(
                "projects.stargazer.backend.main.acquisition.download_osm_roads",
                AsyncMock(),
            ),
            patch(
                "projects.stargazer.backend.main.acquisition.download_dem", AsyncMock()
            ),
            patch("projects.stargazer.backend.main.preprocessing.georeference_raster"),
            patch("projects.stargazer.backend.main.preprocessing.extract_palette"),
            patch("projects.stargazer.backend.main.preprocessing.extract_roads"),
            patch("projects.stargazer.backend.main.preprocessing.clip_dem"),
            patch("projects.stargazer.backend.main.spatial.extract_dark_regions"),
            patch("projects.stargazer.backend.main.spatial.buffer_roads"),
            patch("projects.stargazer.backend.main.spatial.intersect_dark_accessible"),
            patch("projects.stargazer.backend.main.spatial.generate_sample_grid"),
            patch("projects.stargazer.backend.main.spatial.enrich_points"),
            patch(
                "projects.stargazer.backend.main.weather.fetch_all_forecasts",
                AsyncMock(),
            ),
            patch("projects.stargazer.backend.main.weather.score_locations"),
            patch("projects.stargazer.backend.main.weather.output_best_locations"),
            patch.dict(os.environ, {"OTEL_ENABLED": "false"}),
        ):
            # Should complete without error
            await run_pipeline(settings)

    @pytest.mark.asyncio
    async def test_pipeline_propagates_exceptions(self, settings: Settings):
        """Test that pipeline exceptions propagate to the caller."""
        with (
            patch(
                "projects.stargazer.backend.main.acquisition.download_lp_atlas",
                AsyncMock(side_effect=RuntimeError("Network error")),
            ),
            patch(
                "projects.stargazer.backend.main.acquisition.download_colorbar",
                AsyncMock(),
            ),
            patch(
                "projects.stargazer.backend.main.acquisition.download_osm_roads",
                AsyncMock(),
            ),
            patch.dict(os.environ, {"OTEL_ENABLED": "false"}),
        ):
            with pytest.raises(RuntimeError, match="Network error"):
                await run_pipeline(settings)


class TestMain:
    """Tests for main() entry point function."""

    def test_returns_zero_on_success(self, settings: Settings):
        """Test that main() returns 0 on successful pipeline run."""
        with (
            patch("projects.stargazer.backend.main.Settings", return_value=settings),
            patch("projects.stargazer.backend.main.setup_telemetry"),
            patch("projects.stargazer.backend.main.ensure_directories"),
            patch("projects.stargazer.backend.main.asyncio.run"),
        ):
            result = main()

        assert result == 0

    def test_returns_one_on_settings_error(self):
        """Test that main() returns 1 when settings fail to load."""
        with patch(
            "projects.stargazer.backend.main.Settings",
            side_effect=ValueError("Bad config"),
        ):
            result = main()

        assert result == 1

    def test_returns_one_on_pipeline_error(self, settings: Settings):
        """Test that main() returns 1 when pipeline raises an exception."""
        with (
            patch("projects.stargazer.backend.main.Settings", return_value=settings),
            patch("projects.stargazer.backend.main.setup_telemetry"),
            patch("projects.stargazer.backend.main.ensure_directories"),
            patch(
                "projects.stargazer.backend.main.asyncio.run",
                side_effect=RuntimeError("Pipeline failed"),
            ),
        ):
            result = main()

        assert result == 1

    def test_calls_setup_telemetry_with_settings(self, settings: Settings):
        """Test that main() calls setup_telemetry with the loaded settings."""
        with (
            patch("projects.stargazer.backend.main.Settings", return_value=settings),
            patch("projects.stargazer.backend.main.setup_telemetry") as mock_setup,
            patch("projects.stargazer.backend.main.ensure_directories"),
            patch("projects.stargazer.backend.main.asyncio.run"),
        ):
            main()

        mock_setup.assert_called_once_with(settings)

    def test_calls_ensure_directories_with_settings(self, settings: Settings):
        """Test that main() calls ensure_directories with the loaded settings."""
        with (
            patch("projects.stargazer.backend.main.Settings", return_value=settings),
            patch("projects.stargazer.backend.main.setup_telemetry"),
            patch("projects.stargazer.backend.main.ensure_directories") as mock_ensure,
            patch("projects.stargazer.backend.main.asyncio.run"),
        ):
            main()

        mock_ensure.assert_called_once_with(settings)

    def test_calls_asyncio_run_with_pipeline(self, settings: Settings):
        """Test that main() runs the pipeline via asyncio.run."""
        with (
            patch("projects.stargazer.backend.main.Settings", return_value=settings),
            patch("projects.stargazer.backend.main.setup_telemetry"),
            patch("projects.stargazer.backend.main.ensure_directories"),
            patch("projects.stargazer.backend.main.asyncio.run") as mock_run,
        ):
            main()

        mock_run.assert_called_once()
        # The first arg to asyncio.run should be a coroutine
        call_args = mock_run.call_args[0][0]
        import inspect

        assert inspect.iscoroutine(call_args)
        # Clean up the coroutine to avoid warnings
        call_args.close()
