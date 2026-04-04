"""Unit tests for app.log — _HealthzFilter and configure_logging()."""

import logging
from unittest.mock import MagicMock, patch

from app.log import _HealthzFilter, configure_logging


# ---------------------------------------------------------------------------
# _HealthzFilter.filter()
# ---------------------------------------------------------------------------


def test_healthz_filter_suppresses_healthz_message():
    """_HealthzFilter.filter() returns False when message contains '/healthz'."""
    f = _HealthzFilter()
    record = MagicMock(spec=logging.LogRecord)
    record.getMessage.return_value = "GET /healthz HTTP/1.1 200"
    assert f.filter(record) is False


def test_healthz_filter_passes_non_healthz_message():
    """_HealthzFilter.filter() returns True when message does not contain '/healthz'."""
    f = _HealthzFilter()
    record = MagicMock(spec=logging.LogRecord)
    record.getMessage.return_value = "GET /api/todo/daily HTTP/1.1 200"
    assert f.filter(record) is True


def test_healthz_filter_passes_empty_message():
    """_HealthzFilter.filter() returns True for an empty log message."""
    f = _HealthzFilter()
    record = MagicMock(spec=logging.LogRecord)
    record.getMessage.return_value = ""
    assert f.filter(record) is True


def test_healthz_filter_suppresses_healthz_with_query_string():
    """_HealthzFilter.filter() returns False when message contains '/healthz?query=1'."""
    f = _HealthzFilter()
    record = MagicMock(spec=logging.LogRecord)
    record.getMessage.return_value = "GET /healthz?query=1 HTTP/1.1 200"
    assert f.filter(record) is False


def test_healthz_filter_suppresses_exact_healthz_path():
    """_HealthzFilter.filter() returns False when message is exactly '/healthz'."""
    f = _HealthzFilter()
    record = MagicMock(spec=logging.LogRecord)
    record.getMessage.return_value = "/healthz"
    assert f.filter(record) is False


def test_healthz_filter_suppresses_healthz_as_substring():
    """_HealthzFilter.filter() returns False when '/healthz' appears anywhere in message."""
    f = _HealthzFilter()
    record = MagicMock(spec=logging.LogRecord)
    record.getMessage.return_value = "probing /healthz endpoint via k8s"
    assert f.filter(record) is False


# ---------------------------------------------------------------------------
# configure_logging()
# ---------------------------------------------------------------------------


def setup_function():
    """Clear uvicorn.access filters before each test to prevent filter accumulation."""
    logging.getLogger("uvicorn.access").filters.clear()


def test_configure_logging_sets_root_level_debug():
    """configure_logging(logging.DEBUG) sets root logger level to DEBUG."""
    with patch("logging.basicConfig"):
        configure_logging(logging.DEBUG)
    assert logging.getLogger().level == logging.DEBUG


def test_configure_logging_sets_root_level_info():
    """configure_logging(logging.INFO) sets root logger level to INFO."""
    with patch("logging.basicConfig"):
        configure_logging(logging.INFO)
    assert logging.getLogger().level == logging.INFO


def test_configure_logging_sets_root_level_warning():
    """configure_logging(logging.WARNING) sets root logger level to WARNING."""
    with patch("logging.basicConfig"):
        configure_logging(logging.WARNING)
    assert logging.getLogger().level == logging.WARNING


def test_configure_logging_defaults_to_info():
    """configure_logging() without arguments defaults root logger to INFO."""
    with patch("logging.basicConfig"):
        configure_logging()
    assert logging.getLogger().level == logging.INFO


def test_configure_logging_calls_basicconfig_with_level():
    """configure_logging() calls logging.basicConfig with the provided level."""
    with patch("logging.basicConfig") as mock_basicconfig:
        configure_logging(logging.DEBUG)
    mock_basicconfig.assert_called_once()
    kwargs = mock_basicconfig.call_args[1]
    assert kwargs.get("level") == logging.DEBUG


def test_configure_logging_discord_gateway_set_to_warning():
    """configure_logging() sets discord.gateway logger to WARNING."""
    with patch("logging.basicConfig"):
        configure_logging()
    assert logging.getLogger("discord.gateway").level == logging.WARNING


def test_configure_logging_discord_client_set_to_warning():
    """configure_logging() sets discord.client logger to WARNING."""
    with patch("logging.basicConfig"):
        configure_logging()
    assert logging.getLogger("discord.client").level == logging.WARNING


def test_configure_logging_httpx_set_to_warning():
    """configure_logging() sets httpx logger to WARNING."""
    with patch("logging.basicConfig"):
        configure_logging()
    assert logging.getLogger("httpx").level == logging.WARNING


def test_configure_logging_httpcore_set_to_warning():
    """configure_logging() sets httpcore logger to WARNING."""
    with patch("logging.basicConfig"):
        configure_logging()
    assert logging.getLogger("httpcore").level == logging.WARNING


def test_configure_logging_adds_healthz_filter_to_uvicorn_access():
    """configure_logging() attaches a _HealthzFilter to the uvicorn.access logger."""
    with patch("logging.basicConfig"):
        configure_logging()
    uvicorn_access = logging.getLogger("uvicorn.access")
    filter_types = [type(f) for f in uvicorn_access.filters]
    assert _HealthzFilter in filter_types, (
        "Expected _HealthzFilter to be attached to uvicorn.access logger"
    )
