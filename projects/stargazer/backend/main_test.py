"""Unit tests for the main module (pipeline entry point)."""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import projects.stargazer.backend.main as main_module
from projects.stargazer.backend.config import Settings
from projects.stargazer.backend.main import (
    _get_tracer,
    ensure_directories,
    main,
    setup_telemetry,
    trace_span,
)


# ---------------------------------------------------------------------------
# _get_tracer
# ---------------------------------------------------------------------------


class TestGetTracer:
    """Tests for the lazy-initialized global OpenTelemetry tracer."""

    def setup_method(self):
        """Reset global tracer state before each test."""
        main_module._tracer = None

    def teardown_method(self):
        """Reset global tracer state after each test."""
        main_module._tracer = None

    def test_returns_tracer_object(self):
        """_get_tracer() should return a tracer when called."""
        mock_tracer = MagicMock(name="tracer")

        with patch("opentelemetry.trace.get_tracer", return_value=mock_tracer):
            result = _get_tracer()

        assert result is mock_tracer

    def test_sets_global_tracer(self):
        """_get_tracer() should populate the global _tracer variable."""
        mock_tracer = MagicMock(name="tracer")

        with patch("opentelemetry.trace.get_tracer", return_value=mock_tracer):
            _get_tracer()

        assert main_module._tracer is mock_tracer

    def test_caches_tracer_on_second_call(self):
        """_get_tracer() should return the cached tracer on subsequent calls."""
        mock_tracer = MagicMock(name="tracer")

        with patch("opentelemetry.trace.get_tracer", return_value=mock_tracer) as mock_get:
            first = _get_tracer()
            second = _get_tracer()

        assert first is second
        # get_tracer should be called only once — second call uses global cache
        mock_get.assert_called_once()

    def test_preexisting_tracer_skips_initialization(self):
        """If _tracer is already set, get_tracer should not be called again."""
        existing = MagicMock(name="existing_tracer")
        main_module._tracer = existing

        with patch("opentelemetry.trace.get_tracer") as mock_get:
            result = _get_tracer()

        mock_get.assert_not_called()
        assert result is existing


# ---------------------------------------------------------------------------
# trace_span
# ---------------------------------------------------------------------------


class TestTraceSpan:
    """Tests for the trace_span() context manager."""

    def setup_method(self):
        main_module._tracer = None

    def teardown_method(self):
        main_module._tracer = None

    def test_yields_none_when_otel_disabled_lowercase(self):
        """OTEL_ENABLED=false should disable tracing and yield None."""
        with patch.dict(os.environ, {"OTEL_ENABLED": "false"}):
            with trace_span("test.span") as span:
                result = span

        assert result is None

    def test_yields_none_when_otel_disabled_uppercase(self):
        """OTEL_ENABLED=FALSE (uppercase) should also disable tracing."""
        with patch.dict(os.environ, {"OTEL_ENABLED": "FALSE"}):
            with trace_span("test.span") as span:
                result = span

        assert result is None

    def test_yields_none_when_otel_disabled_mixed_case(self):
        """OTEL_ENABLED=False (mixed case) should also disable tracing."""
        with patch.dict(os.environ, {"OTEL_ENABLED": "False"}):
            with trace_span("test.span") as span:
                result = span

        assert result is None

    def test_yields_span_when_otel_enabled(self):
        """When OTEL_ENABLED=true, trace_span should yield the active span."""
        mock_span = MagicMock(name="expected_span")
        mock_tracer = MagicMock(name="tracer")
        mock_tracer.start_as_current_span.return_value.__enter__.return_value = mock_span
        mock_tracer.start_as_current_span.return_value.__exit__.return_value = False

        with patch.dict(os.environ, {"OTEL_ENABLED": "true"}):
            with patch("projects.stargazer.backend.main._get_tracer", return_value=mock_tracer):
                with trace_span("test.span") as span:
                    result = span

        assert result is mock_span

    def test_yields_span_when_otel_enabled_uppercase(self):
        """OTEL_ENABLED=TRUE should enable tracing."""
        mock_span = MagicMock(name="expected_span")
        mock_tracer = MagicMock(name="tracer")
        mock_tracer.start_as_current_span.return_value.__enter__.return_value = mock_span
        mock_tracer.start_as_current_span.return_value.__exit__.return_value = False

        with patch.dict(os.environ, {"OTEL_ENABLED": "TRUE"}):
            with patch("projects.stargazer.backend.main._get_tracer", return_value=mock_tracer):
                with trace_span("test.span") as span:
                    result = span

        assert result is mock_span

    def test_default_otel_enabled_is_true(self):
        """Without OTEL_ENABLED env var, tracing defaults to enabled."""
        mock_tracer = MagicMock(name="tracer")
        mock_tracer.start_as_current_span.return_value.__enter__.return_value = MagicMock()
        mock_tracer.start_as_current_span.return_value.__exit__.return_value = False

        env_without_otel = {k: v for k, v in os.environ.items() if k != "OTEL_ENABLED"}
        with patch.dict(os.environ, env_without_otel, clear=True):
            with patch("projects.stargazer.backend.main._get_tracer", return_value=mock_tracer):
                with trace_span("test.span") as span:
                    result = span

        assert result is not None

    def test_span_name_passed_to_tracer(self):
        """The name argument should be forwarded to start_as_current_span."""
        mock_tracer = MagicMock(name="tracer")
        mock_tracer.start_as_current_span.return_value.__enter__.return_value = MagicMock()
        mock_tracer.start_as_current_span.return_value.__exit__.return_value = False

        with patch.dict(os.environ, {"OTEL_ENABLED": "true"}):
            with patch("projects.stargazer.backend.main._get_tracer", return_value=mock_tracer):
                with trace_span("my.pipeline.phase"):
                    pass

        mock_tracer.start_as_current_span.assert_called_once_with("my.pipeline.phase")


# ---------------------------------------------------------------------------
# setup_telemetry
# ---------------------------------------------------------------------------


class TestSetupTelemetry:
    """Tests for setup_telemetry() configuring the OTEL tracer provider."""

    def _make_settings(self, **kwargs) -> Settings:
        defaults: dict = {"data_dir": Path("/tmp")}
        defaults.update(kwargs)
        return Settings(**defaults)

    def test_returns_early_when_otel_disabled(self):
        """setup_telemetry should return immediately when otel_enabled=False."""
        settings = self._make_settings(otel_enabled=False)
        # No imports or side-effects — no errors is the assertion
        setup_telemetry(settings)

    def test_logs_info_when_otel_disabled(self):
        """setup_telemetry should log an info message when tracing is disabled."""
        settings = self._make_settings(otel_enabled=False)

        with patch("projects.stargazer.backend.main.logger") as mock_logger:
            setup_telemetry(settings)

        mock_logger.info.assert_called_once()
        assert "disabled" in mock_logger.info.call_args[0][0].lower()

    def test_handles_import_error_gracefully(self):
        """setup_telemetry should log a warning and return if OTEL packages are missing."""
        settings = self._make_settings(
            otel_enabled=True,
            otel_exporter_otlp_endpoint="http://otel:4317",
        )

        # Block opentelemetry imports by setting entries to None in sys.modules
        blocked = {key: None for key in sys.modules if key.startswith("opentelemetry")}
        blocked.setdefault("opentelemetry", None)

        with patch.dict(sys.modules, blocked):
            with patch("projects.stargazer.backend.main.logger") as mock_logger:
                setup_telemetry(settings)

        mock_logger.warning.assert_called()
        warning_msg = mock_logger.warning.call_args[0][0]
        assert "not available" in warning_msg.lower() or "opentelemetry" in warning_msg.lower()

    def test_warns_when_no_otlp_endpoint_configured(self):
        """setup_telemetry should warn when otel_enabled but endpoint is empty."""
        settings = self._make_settings(otel_enabled=True, otel_exporter_otlp_endpoint="")

        with (
            patch("opentelemetry.sdk.trace.TracerProvider"),
            patch("opentelemetry.sdk.resources.Resource"),
            patch("opentelemetry.trace.set_tracer_provider"),
            patch("projects.stargazer.backend.main.logger") as mock_logger,
        ):
            setup_telemetry(settings)

        mock_logger.warning.assert_called()
        warning_calls = " ".join(str(c) for c in mock_logger.warning.call_args_list)
        assert "endpoint" in warning_calls.lower()

    def test_happy_path_sets_global_tracer_provider(self):
        """setup_telemetry should configure and register the tracer provider."""
        settings = self._make_settings(
            otel_enabled=True,
            otel_exporter_otlp_endpoint="http://otel:4317",
        )

        mock_provider_inst = MagicMock(name="provider_instance")

        with (
            patch("opentelemetry.sdk.trace.TracerProvider", return_value=mock_provider_inst),
            patch("opentelemetry.exporter.otlp.proto.grpc.trace_exporter.OTLPSpanExporter"),
            patch("opentelemetry.sdk.trace.export.BatchSpanProcessor"),
            patch("opentelemetry.sdk.resources.Resource"),
            patch("opentelemetry.trace.set_tracer_provider") as mock_set_provider,
        ):
            setup_telemetry(settings)

        mock_set_provider.assert_called_once_with(mock_provider_inst)

    def test_happy_path_adds_span_processor(self):
        """setup_telemetry should add a BatchSpanProcessor when endpoint is set."""
        settings = self._make_settings(
            otel_enabled=True,
            otel_exporter_otlp_endpoint="http://otel:4317",
        )

        mock_provider_inst = MagicMock(name="provider_instance")

        with (
            patch("opentelemetry.sdk.trace.TracerProvider", return_value=mock_provider_inst),
            patch("opentelemetry.exporter.otlp.proto.grpc.trace_exporter.OTLPSpanExporter"),
            patch("opentelemetry.sdk.trace.export.BatchSpanProcessor"),
            patch("opentelemetry.sdk.resources.Resource"),
            patch("opentelemetry.trace.set_tracer_provider"),
        ):
            setup_telemetry(settings)

        mock_provider_inst.add_span_processor.assert_called_once()

    def test_no_span_processor_without_endpoint(self):
        """Without an OTLP endpoint, no span processor should be added."""
        settings = self._make_settings(otel_enabled=True, otel_exporter_otlp_endpoint="")

        mock_provider_inst = MagicMock(name="provider_instance")

        with (
            patch("opentelemetry.sdk.trace.TracerProvider", return_value=mock_provider_inst),
            patch("opentelemetry.sdk.resources.Resource"),
            patch("opentelemetry.trace.set_tracer_provider"),
        ):
            setup_telemetry(settings)

        mock_provider_inst.add_span_processor.assert_not_called()

    def test_happy_path_logs_info(self):
        """setup_telemetry should log info on successful configuration."""
        settings = self._make_settings(
            otel_enabled=True,
            otel_exporter_otlp_endpoint="http://otel:4317",
        )

        with (
            patch("opentelemetry.sdk.trace.TracerProvider"),
            patch("opentelemetry.exporter.otlp.proto.grpc.trace_exporter.OTLPSpanExporter"),
            patch("opentelemetry.sdk.trace.export.BatchSpanProcessor"),
            patch("opentelemetry.sdk.resources.Resource"),
            patch("opentelemetry.trace.set_tracer_provider"),
            patch("projects.stargazer.backend.main.logger") as mock_logger,
        ):
            setup_telemetry(settings)

        mock_logger.info.assert_called()

    def test_resource_created_with_service_name(self):
        """setup_telemetry should create a Resource with the configured service name."""
        settings = self._make_settings(
            otel_enabled=True,
            otel_exporter_otlp_endpoint="http://otel:4317",
            otel_service_name="my-stargazer",
        )

        with (
            patch("opentelemetry.sdk.trace.TracerProvider"),
            patch("opentelemetry.exporter.otlp.proto.grpc.trace_exporter.OTLPSpanExporter"),
            patch("opentelemetry.sdk.trace.export.BatchSpanProcessor"),
            patch("opentelemetry.sdk.resources.Resource") as mock_resource_cls,
            patch("opentelemetry.trace.set_tracer_provider"),
        ):
            setup_telemetry(settings)

        call_kwargs = mock_resource_cls.create.call_args[0][0]
        assert call_kwargs.get("service.name") == "my-stargazer"


# ---------------------------------------------------------------------------
# ensure_directories
# ---------------------------------------------------------------------------


class TestEnsureDirectories:
    """Tests for ensure_directories() creating the data directory layout."""

    def test_creates_raw_dir(self, tmp_path):
        settings = Settings(data_dir=tmp_path)
        ensure_directories(settings)
        assert settings.raw_dir.exists()

    def test_creates_processed_dir(self, tmp_path):
        settings = Settings(data_dir=tmp_path)
        ensure_directories(settings)
        assert settings.processed_dir.exists()

    def test_creates_cache_dir(self, tmp_path):
        settings = Settings(data_dir=tmp_path)
        ensure_directories(settings)
        assert settings.cache_dir.exists()

    def test_creates_output_dir(self, tmp_path):
        settings = Settings(data_dir=tmp_path)
        ensure_directories(settings)
        assert settings.output_dir.exists()

    def test_all_four_directories_are_created(self, tmp_path):
        settings = Settings(data_dir=tmp_path)
        ensure_directories(settings)
        for directory in [
            settings.raw_dir,
            settings.processed_dir,
            settings.cache_dir,
            settings.output_dir,
        ]:
            assert directory.is_dir(), f"{directory} was not created"

    def test_idempotent_when_directories_already_exist(self, tmp_path):
        """Calling ensure_directories twice should not raise any exceptions."""
        settings = Settings(data_dir=tmp_path)
        ensure_directories(settings)
        ensure_directories(settings)  # Should not raise

    def test_creates_nested_parent_directories(self, tmp_path):
        """ensure_directories should create missing parent directories."""
        nested = tmp_path / "deep" / "nested" / "path"
        settings = Settings(data_dir=nested)
        ensure_directories(settings)
        assert settings.raw_dir.is_dir()

    def test_raw_dir_is_actual_directory(self, tmp_path):
        """raw_dir should be a directory, not a file."""
        settings = Settings(data_dir=tmp_path)
        ensure_directories(settings)
        assert settings.raw_dir.is_dir()
        assert not settings.raw_dir.is_file()


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------


class TestMain:
    """Tests for the main() entry point."""

    def _make_settings(self, tmp_path: Path) -> Settings:
        return Settings(data_dir=tmp_path, otel_enabled=False)

    def test_returns_one_on_settings_load_failure(self):
        """main() should return 1 when Settings() raises an exception."""
        with patch("projects.stargazer.backend.main.Settings", side_effect=Exception("bad env")):
            result = main()

        assert result == 1

    def test_returns_one_on_validation_error(self):
        """main() should return 1 when Settings() raises a validation error."""
        with patch("projects.stargazer.backend.main.Settings", side_effect=ValueError("invalid field")):
            result = main()

        assert result == 1

    def test_returns_one_on_pipeline_exception(self, tmp_path):
        """main() should return 1 when the pipeline raises an exception."""
        settings = self._make_settings(tmp_path)

        with (
            patch("projects.stargazer.backend.main.Settings", return_value=settings),
            patch("projects.stargazer.backend.main.setup_telemetry"),
            patch("projects.stargazer.backend.main.ensure_directories"),
            patch("projects.stargazer.backend.main.asyncio.run", side_effect=RuntimeError("boom")),
        ):
            result = main()

        assert result == 1

    def test_returns_zero_on_success(self, tmp_path):
        """main() should return 0 on successful pipeline execution."""
        settings = self._make_settings(tmp_path)

        with (
            patch("projects.stargazer.backend.main.Settings", return_value=settings),
            patch("projects.stargazer.backend.main.setup_telemetry"),
            patch("projects.stargazer.backend.main.ensure_directories"),
            patch("projects.stargazer.backend.main.asyncio.run"),
        ):
            result = main()

        assert result == 0

    def test_calls_setup_telemetry_with_settings(self, tmp_path):
        """main() should call setup_telemetry() with the loaded settings object."""
        settings = self._make_settings(tmp_path)

        with (
            patch("projects.stargazer.backend.main.Settings", return_value=settings),
            patch("projects.stargazer.backend.main.setup_telemetry") as mock_setup,
            patch("projects.stargazer.backend.main.ensure_directories"),
            patch("projects.stargazer.backend.main.asyncio.run"),
        ):
            main()

        mock_setup.assert_called_once_with(settings)

    def test_calls_ensure_directories_with_settings(self, tmp_path):
        """main() should call ensure_directories() with the loaded settings object."""
        settings = self._make_settings(tmp_path)

        with (
            patch("projects.stargazer.backend.main.Settings", return_value=settings),
            patch("projects.stargazer.backend.main.setup_telemetry"),
            patch("projects.stargazer.backend.main.ensure_directories") as mock_dirs,
            patch("projects.stargazer.backend.main.asyncio.run"),
        ):
            main()

        mock_dirs.assert_called_once_with(settings)

    def test_settings_failure_skips_setup_telemetry(self):
        """If Settings() fails, setup_telemetry should not be called."""
        with (
            patch("projects.stargazer.backend.main.Settings", side_effect=ValueError("bad")),
            patch("projects.stargazer.backend.main.setup_telemetry") as mock_setup,
        ):
            main()

        mock_setup.assert_not_called()

    def test_settings_failure_skips_ensure_directories(self):
        """If Settings() fails, ensure_directories should not be called."""
        with (
            patch("projects.stargazer.backend.main.Settings", side_effect=ValueError("bad")),
            patch("projects.stargazer.backend.main.ensure_directories") as mock_dirs,
        ):
            main()

        mock_dirs.assert_not_called()

    def test_calls_asyncio_run(self, tmp_path):
        """main() should call asyncio.run() to execute the async pipeline."""
        settings = self._make_settings(tmp_path)

        with (
            patch("projects.stargazer.backend.main.Settings", return_value=settings),
            patch("projects.stargazer.backend.main.setup_telemetry"),
            patch("projects.stargazer.backend.main.ensure_directories"),
            patch("projects.stargazer.backend.main.asyncio.run") as mock_run,
        ):
            main()

        mock_run.assert_called_once()
