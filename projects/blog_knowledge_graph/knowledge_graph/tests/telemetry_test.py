"""Tests for OpenTelemetry telemetry setup."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

import projects.blog_knowledge_graph.knowledge_graph.app.telemetry as telemetry_module
from projects.blog_knowledge_graph.knowledge_graph.app.telemetry import (
    setup_telemetry,
    trace_span,
)


class TestTraceSpan:
    def test_yields_none_when_otel_disabled(self, monkeypatch):
        monkeypatch.setenv("OTEL_ENABLED", "false")

        with trace_span("test-span") as span:
            assert span is None

    def test_yields_none_when_otel_disabled_uppercase(self, monkeypatch):
        monkeypatch.setenv("OTEL_ENABLED", "FALSE")

        with trace_span("test-span") as span:
            assert span is None

    def test_yields_span_when_otel_enabled(self, monkeypatch):
        monkeypatch.setenv("OTEL_ENABLED", "true")
        mock_span = MagicMock()
        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(
            return_value=mock_span
        )
        mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(
            return_value=False
        )

        with patch.object(telemetry_module, "_get_tracer", return_value=mock_tracer):
            with trace_span("my-span") as span:
                assert span is mock_span
            mock_tracer.start_as_current_span.assert_called_once_with("my-span")

    def test_default_otel_is_enabled(self, monkeypatch):
        monkeypatch.delenv("OTEL_ENABLED", raising=False)
        mock_span = MagicMock()
        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(
            return_value=mock_span
        )
        mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(
            return_value=False
        )

        # Default is true when env var is absent — _get_tracer should be called
        with patch.object(telemetry_module, "_get_tracer", return_value=mock_tracer):
            with trace_span("default-span") as span:
                assert span is mock_span

    def test_span_name_propagated(self, monkeypatch):
        monkeypatch.setenv("OTEL_ENABLED", "true")
        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(
            return_value=MagicMock()
        )
        mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(
            return_value=False
        )

        with patch.object(telemetry_module, "_get_tracer", return_value=mock_tracer):
            with trace_span("embed:abc123456789"):
                pass
            mock_tracer.start_as_current_span.assert_called_once_with(
                "embed:abc123456789"
            )

    def test_trace_span_is_context_manager(self, monkeypatch):
        monkeypatch.setenv("OTEL_ENABLED", "false")
        # Verify it can be used as a context manager and doesn't raise
        with trace_span("ctx-test"):
            pass  # Should not raise


class TestGetTracer:
    def test_returns_tracer_object(self, monkeypatch):
        # Reset the cached tracer so _get_tracer initialises fresh
        original = telemetry_module._tracer
        telemetry_module._tracer = None
        try:
            tracer = telemetry_module._get_tracer()
            assert tracer is not None
        finally:
            telemetry_module._tracer = original

    def test_caches_tracer_across_calls(self, monkeypatch):
        original = telemetry_module._tracer
        telemetry_module._tracer = None
        try:
            t1 = telemetry_module._get_tracer()
            t2 = telemetry_module._get_tracer()
            assert t1 is t2
        finally:
            telemetry_module._tracer = original


class TestSetupTelemetry:
    def test_logs_disabled_when_otel_off(self, monkeypatch, caplog):
        monkeypatch.setenv("OTEL_ENABLED", "false")

        with caplog.at_level(logging.INFO):
            setup_telemetry("test-service")

        assert any("disabled" in record.message.lower() for record in caplog.records)

    def test_no_error_when_disabled(self, monkeypatch):
        monkeypatch.setenv("OTEL_ENABLED", "false")
        # Must not raise regardless of service name
        setup_telemetry("any-service-name")

    def test_no_error_when_enabled_no_endpoint(self, monkeypatch):
        monkeypatch.setenv("OTEL_ENABLED", "true")
        # No OTLP endpoint — provider is configured but no exporter added
        setup_telemetry("test-service", otlp_endpoint="")

    def test_enabled_logs_endpoint(self, monkeypatch, caplog):
        monkeypatch.setenv("OTEL_ENABLED", "true")

        with caplog.at_level(logging.INFO):
            setup_telemetry("test-service", otlp_endpoint="http://otel:4317")

        assert any("otel" in record.message.lower() for record in caplog.records)

    def test_uppercase_false_is_disabled(self, monkeypatch, caplog):
        monkeypatch.setenv("OTEL_ENABLED", "FALSE")

        with caplog.at_level(logging.INFO):
            setup_telemetry("svc")

        assert any("disabled" in record.message.lower() for record in caplog.records)
