"""Coverage for app.main -- OpenTelemetry instrumentation success branch.

This test file must be isolated from main_test.py and main_coverage_test.py because
the OTEL instrumentation block in app/main.py runs at module-import time. We exercise
the success branch by reloading the module with a mocked opentelemetry package.
"""

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
