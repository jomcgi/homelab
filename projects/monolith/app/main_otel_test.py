"""Coverage for app.main -- OpenTelemetry instrumentation branches.

This test file must be isolated from main_test.py and main_coverage_test.py because
the OTEL instrumentation block in app/main.py runs at module-import time.  We exercise
the success branch by reloading the module with a mocked opentelemetry package, and
the ImportError branch by forcing the import to fail.

Uses importlib.reload() instead of pop-and-reimport because app.main transitively
imports C extension modules (numpy via pydantic_ai) that cannot be loaded twice.
"""

import importlib
import logging
import os
import sys
from unittest.mock import MagicMock, patch

# Ensure no valid STATIC_DIR is set so the StaticFiles mount is skipped.
os.environ.pop("STATIC_DIR", None)

# Force an initial import so reload() has something to work with.
import app.main  # noqa: F401, E402


def _make_otel_fake_modules():
    """Build fake sys.modules entries for all opentelemetry subpackages used by main.py."""
    mock_instrumentor_class = MagicMock()
    mock_instrumentor_class.instrument_app = MagicMock()

    mock_fastapi_module = MagicMock()
    mock_fastapi_module.FastAPIInstrumentor = mock_instrumentor_class

    mock_trace = MagicMock()

    # Inject fakes for all OTEL subpackages imported by main.py.
    # Do NOT replace the root opentelemetry package — pydantic_ai and other
    # transitive deps import opentelemetry.trace, opentelemetry.baggage, etc.
    return {
        "opentelemetry.exporter": MagicMock(),
        "opentelemetry.exporter.otlp": MagicMock(),
        "opentelemetry.exporter.otlp.proto": MagicMock(),
        "opentelemetry.exporter.otlp.proto.http": MagicMock(),
        "opentelemetry.exporter.otlp.proto.http.trace_exporter": MagicMock(),
        "opentelemetry.instrumentation": MagicMock(),
        "opentelemetry.instrumentation.fastapi": mock_fastapi_module,
        "opentelemetry.sdk": MagicMock(),
        "opentelemetry.sdk.resources": MagicMock(),
        "opentelemetry.sdk.trace": MagicMock(),
        "opentelemetry.sdk.trace.export": MagicMock(),
    }, mock_instrumentor_class


class TestOtelInstrumentationSuccessBranch:
    def test_instrument_app_called_when_opentelemetry_available(self):
        """FastAPIInstrumentor.instrument_app() is called when the package is present."""
        fake_modules, mock_instrumentor_class = _make_otel_fake_modules()

        with patch.dict(sys.modules, fake_modules):
            importlib.reload(app.main)

        mock_instrumentor_class.instrument_app.assert_called_once()


class TestOtelInstrumentationImportErrorBranch:
    """Verify the except ImportError branch in the OTEL block.

    Setting entries to ``None`` in ``sys.modules`` causes Python to raise
    ``ImportError`` when that module is imported, which mimics the production
    environment where the opentelemetry instrumentation package is absent.
    """

    def _reload_main_without_otel(self):
        """Reload app.main with opentelemetry instrumentation blocked."""
        # Only block the instrumentation/SDK/exporter subpackages (not the root
        # opentelemetry package) because pydantic_ai imports opentelemetry.trace
        # at import time and would fail if the root package were blocked.
        blocked = {
            "opentelemetry.exporter": None,
            "opentelemetry.exporter.otlp": None,
            "opentelemetry.exporter.otlp.proto": None,
            "opentelemetry.exporter.otlp.proto.http": None,
            "opentelemetry.exporter.otlp.proto.http.trace_exporter": None,
            "opentelemetry.instrumentation": None,
            "opentelemetry.instrumentation.fastapi": None,
            "opentelemetry.sdk": None,
            "opentelemetry.sdk.resources": None,
            "opentelemetry.sdk.trace": None,
            "opentelemetry.sdk.trace.export": None,
        }

        log_records: list[logging.LogRecord] = []

        class _Capture(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                log_records.append(record)

        target_logger = logging.getLogger("app.main")
        handler = _Capture()
        target_logger.addHandler(handler)
        try:
            with patch.dict(sys.modules, blocked):
                importlib.reload(app.main)
        finally:
            target_logger.removeHandler(handler)

        return log_records

    def test_import_error_branch_does_not_raise(self):
        """app.main loads successfully when opentelemetry instrumentation is unavailable."""
        records = self._reload_main_without_otel()
        assert records is not None

    def test_import_error_branch_logs_not_available_message(self):
        """When opentelemetry instrumentation is absent the 'not available' message is logged."""
        records = self._reload_main_without_otel()
        messages = [r.getMessage() for r in records]
        assert any("OpenTelemetry not available" in m for m in messages), (
            f"Expected 'OpenTelemetry not available' in logged messages; got: {messages}"
        )

    def test_import_error_branch_does_not_log_enabled_message(self):
        """The 'instrumentation enabled' message must NOT appear when otel is absent."""
        records = self._reload_main_without_otel()
        messages = [r.getMessage() for r in records]
        assert not any("instrumentation enabled" in m for m in messages), (
            "Did not expect 'instrumentation enabled' when opentelemetry is unavailable"
        )
