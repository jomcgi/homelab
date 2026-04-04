"""Coverage for app.main -- OpenTelemetry instrumentation branches.

This test file must be isolated from main_test.py and main_coverage_test.py because
the OTEL instrumentation block in app/main.py runs at module-import time.  We exercise
the success branch by reloading the module with a mocked opentelemetry package, and
the ImportError branch by forcing the import to fail.
"""

import logging
import os
import sys
from unittest.mock import MagicMock, patch

# Ensure no valid STATIC_DIR is set so the StaticFiles mount is skipped.
os.environ.pop("STATIC_DIR", None)


class TestOtelInstrumentationSuccessBranch:
    def test_instrument_app_called_when_opentelemetry_available(self):
        """FastAPIInstrumentor.instrument_app() is called when the package is present."""
        mock_instrumentor_class = MagicMock()
        mock_instrumentor_class.instrument_app = MagicMock()

        mock_otel_module = MagicMock()
        mock_otel_module.FastAPIInstrumentor = mock_instrumentor_class

        # Inject a fake opentelemetry.instrumentation.fastapi into sys.modules
        # so that the `from opentelemetry.instrumentation.fastapi import ...` succeeds.
        fake_modules = {
            "opentelemetry": MagicMock(),
            "opentelemetry.instrumentation": MagicMock(),
            "opentelemetry.instrumentation.fastapi": mock_otel_module,
        }

        # Remove app.main from sys.modules so it will be freshly imported.
        # Keep app itself (the package) but drop the main submodule.
        sys.modules.pop("app.main", None)

        with patch.dict(sys.modules, fake_modules):
            import app.main  # noqa: F401

        mock_instrumentor_class.instrument_app.assert_called_once()

    def teardown_method(self, method):
        """Clean up app.main from sys.modules after the test."""
        sys.modules.pop("app.main", None)


class TestOtelInstrumentationImportErrorBranch:
    """Verify the except ImportError branch in the OTEL block (lines 93-94 of main.py).

    Setting a module to ``None`` in ``sys.modules`` causes Python to raise
    ``ImportError`` when that module is imported, which mimics the production
    environment where the opentelemetry package is absent.
    """

    def _load_main_without_otel(self):
        """Remove app.main from the module cache and reimport it with otel blocked."""
        sys.modules.pop("app.main", None)

        # Setting entries to None makes Python raise ImportError on import.
        blocked = {
            "opentelemetry": None,
            "opentelemetry.instrumentation": None,
            "opentelemetry.instrumentation.fastapi": None,
        }

        log_records: list[logging.LogRecord] = []

        class _Capture(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                log_records.append(record)

        # Attach the capture handler to the logger *before* importing so we
        # catch messages emitted during module-level execution.
        target_logger = logging.getLogger("app.main")
        handler = _Capture()
        target_logger.addHandler(handler)
        try:
            with patch.dict(sys.modules, blocked):
                import app.main as _m  # noqa: F401
        finally:
            target_logger.removeHandler(handler)

        return log_records

    def test_import_error_branch_does_not_raise(self):
        """app.main loads successfully when opentelemetry is unavailable."""
        # Should not raise — the ImportError is caught by the try/except block.
        records = self._load_main_without_otel()
        # Reaching here means no uncaught ImportError escaped.
        assert records is not None  # trivially true; import succeeded

    def test_import_error_branch_logs_not_available_message(self):
        """When opentelemetry is absent the 'not available' info message is logged."""
        records = self._load_main_without_otel()
        messages = [r.getMessage() for r in records]
        assert any("OpenTelemetry not available" in m for m in messages), (
            f"Expected 'OpenTelemetry not available' in logged messages; got: {messages}"
        )

    def test_import_error_branch_does_not_log_enabled_message(self):
        """The 'instrumentation enabled' message must NOT appear when otel is absent."""
        records = self._load_main_without_otel()
        messages = [r.getMessage() for r in records]
        assert not any("instrumentation enabled" in m for m in messages), (
            "Did not expect 'instrumentation enabled' when opentelemetry is unavailable"
        )

    def teardown_method(self, method):
        """Clean up app.main from sys.modules after each test."""
        sys.modules.pop("app.main", None)
