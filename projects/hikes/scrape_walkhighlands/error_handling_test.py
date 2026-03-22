"""Tests for error handling utilities."""

import logging
import sqlite3
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from projects.hikes.scrape_walkhighlands.error_handling import (
    AppError,
    ConfigurationError,
    DatabaseError,
    DataValidationError,
    ErrorCollector,
    NetworkError,
    create_error_context,
    ensure_directory_exists,
    graceful_shutdown,
    handle_network_errors,
    log_performance,
    retry_on_failure,
    safe_database_operation,
    safe_float_conversion,
    safe_int_conversion,
    validate_database_file,
    with_error_collection,
)


class TestExceptions:
    """Tests for custom exception classes."""

    def test_app_error_default_recoverable(self):
        error = AppError("test error")
        assert str(error) == "test error"
        assert error.recoverable is True

    def test_app_error_non_recoverable(self):
        error = AppError("critical error", recoverable=False)
        assert error.recoverable is False

    def test_database_error(self):
        error = DatabaseError("db error")
        assert isinstance(error, AppError)
        assert error.recoverable is True

    def test_network_error(self):
        error = NetworkError("connection failed")
        assert isinstance(error, AppError)

    def test_configuration_error_not_recoverable(self):
        error = ConfigurationError("bad config")
        assert isinstance(error, AppError)
        assert error.recoverable is False

    def test_data_validation_error(self):
        error = DataValidationError("invalid data")
        assert isinstance(error, AppError)


class TestRetryOnFailure:
    """Tests for retry decorator."""

    def test_success_first_try(self):
        call_count = 0

        @retry_on_failure(max_retries=3)
        def always_succeeds():
            nonlocal call_count
            call_count += 1
            return "success"

        result = always_succeeds()

        assert result == "success"
        assert call_count == 1

    def test_success_after_retries(self):
        call_count = 0

        @retry_on_failure(max_retries=3, delay=0.01)
        def fails_twice():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("temporary error")
            return "success"

        result = fails_twice()

        assert result == "success"
        assert call_count == 3

    def test_exhausted_retries(self):
        call_count = 0

        @retry_on_failure(max_retries=2, delay=0.01)
        def always_fails():
            nonlocal call_count
            call_count += 1
            raise ValueError("permanent error")

        with pytest.raises(ValueError, match="permanent error"):
            always_fails()

        assert call_count == 3  # Initial + 2 retries

    def test_specific_exceptions(self):
        """Only specified exceptions trigger retry."""
        call_count = 0

        @retry_on_failure(max_retries=3, delay=0.01, exceptions=(ValueError,))
        def raises_type_error():
            nonlocal call_count
            call_count += 1
            raise TypeError("wrong type")

        with pytest.raises(TypeError):
            raises_type_error()

        assert call_count == 1  # No retries for TypeError


class TestSafeDatabaseOperation:
    """Tests for database operation wrapper."""

    def test_success(self):
        @safe_database_operation
        def query():
            return [1, 2, 3]

        result = query()
        assert result == [1, 2, 3]

    def test_sqlite_error_returns_none(self):
        @safe_database_operation
        def failing_query():
            raise sqlite3.Error("database locked")

        result = failing_query()
        assert result is None

    def test_other_error_returns_none(self):
        @safe_database_operation
        def failing_operation():
            raise Exception("unexpected error")

        result = failing_operation()
        assert result is None


class TestEnsureDirectoryExists:
    """Tests for directory creation utility."""

    def test_create_new_directory(self, tmp_path):
        new_dir = tmp_path / "new_subdir" / "nested"
        assert not new_dir.exists()

        result = ensure_directory_exists(new_dir)

        assert result is True
        assert new_dir.exists()

    def test_existing_directory(self, tmp_path):
        result = ensure_directory_exists(tmp_path)

        assert result is True
        assert tmp_path.exists()

    def test_permission_error(self):
        with patch.object(Path, "mkdir", side_effect=PermissionError("denied")):
            result = ensure_directory_exists(Path("/some/path"))
            assert result is False


class TestValidateDatabaseFile:
    """Tests for database validation."""

    def test_valid_database(self, tmp_path):
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE test (id INTEGER)")
        conn.close()

        result = validate_database_file(str(db_path))
        assert result is True

    def test_nonexistent_database(self, tmp_path):
        db_path = tmp_path / "nonexistent.db"

        result = validate_database_file(str(db_path))
        assert result is False

    def test_corrupted_database(self, tmp_path):
        db_path = tmp_path / "corrupted.db"
        db_path.write_text("not a valid sqlite database")

        result = validate_database_file(str(db_path))
        assert result is False


class TestGracefulShutdown:
    """Tests for graceful shutdown decorator."""

    def test_success(self):
        @graceful_shutdown
        def normal_operation():
            return "done"

        result = normal_operation()
        assert result == "done"

    def test_keyboard_interrupt(self):
        @graceful_shutdown
        def interrupted():
            raise KeyboardInterrupt()

        result = interrupted()
        assert result is None

    def test_configuration_error(self):
        @graceful_shutdown
        def bad_config():
            raise ConfigurationError("missing required config")

        result = bad_config()
        assert result is None

    def test_other_exception(self):
        @graceful_shutdown
        def failing_operation():
            raise Exception("unexpected")

        result = failing_operation()
        assert result is None


class TestHandleNetworkErrors:
    """Tests for network error handling decorator."""

    def test_success(self):
        @handle_network_errors
        def fetch_data():
            return {"data": "value"}

        result = fetch_data()
        assert result == {"data": "value"}

    def test_connection_error(self):
        @handle_network_errors
        def failing_fetch():
            raise ConnectionError("connection refused")

        result = failing_fetch()
        assert result is None

    def test_timeout_error(self):
        @handle_network_errors
        def slow_fetch():
            raise TimeoutError("request timed out")

        result = slow_fetch()
        assert result is None


class TestLogPerformance:
    """Tests for performance logging decorator."""

    def test_logs_duration(self, caplog):
        @log_performance
        def timed_operation():
            return "result"

        with caplog.at_level(logging.DEBUG):
            result = timed_operation()

        assert result == "result"
        assert "timed_operation" in caplog.text
        assert "completed in" in caplog.text

    def test_logs_failure_duration(self, caplog):
        @log_performance
        def failing_operation():
            raise ValueError("error")

        with caplog.at_level(logging.WARNING):
            with pytest.raises(ValueError):
                failing_operation()

        assert "failing_operation" in caplog.text
        assert "failed after" in caplog.text


class TestSafeConversions:
    """Tests for safe type conversion functions."""

    def test_safe_int_conversion_valid(self):
        assert safe_int_conversion("42") == 42
        assert safe_int_conversion(42.7) == 42

    def test_safe_int_conversion_invalid(self):
        assert safe_int_conversion("not a number") == 0
        assert safe_int_conversion(None) == 0

    def test_safe_int_conversion_custom_default(self):
        assert safe_int_conversion("invalid", default=-1) == -1

    def test_safe_float_conversion_valid(self):
        assert safe_float_conversion("3.14") == pytest.approx(3.14)
        assert safe_float_conversion(42) == 42.0

    def test_safe_float_conversion_invalid(self):
        assert safe_float_conversion("not a number") == 0.0
        assert safe_float_conversion(None) == 0.0

    def test_safe_float_conversion_custom_default(self):
        assert safe_float_conversion("invalid", default=-1.0) == -1.0


class TestCreateErrorContext:
    """Tests for error context creation."""

    def test_basic_context(self):
        context = create_error_context("fetch_data")

        assert context["operation"] == "fetch_data"
        assert "timestamp" in context

    def test_context_with_extra_info(self):
        context = create_error_context(
            "fetch_data", url="https://example.com", retry_count=3
        )

        assert context["operation"] == "fetch_data"
        assert context["url"] == "https://example.com"
        assert context["retry_count"] == 3


class TestErrorCollector:
    """Tests for ErrorCollector class."""

    def test_empty_collector(self):
        collector = ErrorCollector()

        assert collector.has_errors() is False
        assert collector.get_summary() == "No errors"

    def test_add_error(self):
        collector = ErrorCollector()
        collector.add_error("operation1", ValueError("test error"), key="value")

        assert collector.has_errors() is True
        assert len(collector.errors) == 1
        assert collector.errors[0]["operation"] == "operation1"
        assert collector.errors[0]["error_type"] == "ValueError"
        assert collector.errors[0]["key"] == "value"

    def test_get_summary_with_errors(self):
        collector = ErrorCollector()
        collector.add_error("op1", ValueError("error1"))
        collector.add_error("op2", ValueError("error2"))
        collector.add_error("op3", TypeError("error3"))

        summary = collector.get_summary()

        assert "3 errors" in summary
        assert "ValueError" in summary
        assert "TypeError" in summary

    def test_log_summary_with_errors(self, caplog):
        collector = ErrorCollector()
        collector.add_error("op1", ValueError("error"))

        with caplog.at_level(logging.WARNING):
            collector.log_summary()

        assert "Collected" in caplog.text

    def test_log_summary_no_errors(self, caplog):
        collector = ErrorCollector()

        with caplog.at_level(logging.INFO):
            collector.log_summary()

        assert "without errors" in caplog.text


class TestWithErrorCollection:
    """Tests for the with_error_collection decorator."""

    def test_logger_exception_called_when_func_raises(self):
        """logger.exception must be called in with_error_collection when func raises."""

        @with_error_collection
        def failing_func(error_collector):
            raise ValueError("test error")

        with patch(
            "projects.hikes.scrape_walkhighlands.error_handling.logger"
        ) as mock_logger:
            result, collector = failing_func()

        mock_logger.exception.assert_called_once()
        assert "failing_func" in str(mock_logger.exception.call_args)
        assert result is None

    def test_returns_none_and_nonempty_error_collector_on_exception(self):
        """Returns (None, non-empty ErrorCollector) when func raises."""

        @with_error_collection
        def failing_func(error_collector):
            raise RuntimeError("something failed")

        result, collector = failing_func()

        assert result is None
        assert collector.has_errors()
        assert len(collector.errors) == 1

    def test_error_collector_contains_error_info(self):
        """The ErrorCollector returned includes the function name and exception."""

        @with_error_collection
        def my_func(error_collector):
            raise TypeError("bad type")

        result, collector = my_func()

        assert collector.errors[0]["operation"] == "my_func"
        assert "TypeError" in collector.errors[0]["error_type"]

    def test_happy_path_returns_result_and_empty_collector(self):
        """When func succeeds, returns (result, empty ErrorCollector)."""

        @with_error_collection
        def ok_func(error_collector):
            return 42

        result, collector = ok_func()

        assert result == 42
        assert not collector.has_errors()

    def test_logger_exception_message_contains_func_name(self):
        """The logger.exception format string includes the function name."""

        @with_error_collection
        def named_func(error_collector):
            raise ValueError("boom")

        with patch(
            "projects.hikes.scrape_walkhighlands.error_handling.logger"
        ) as mock_logger:
            failing_func_name = "named_func"
            named_func()

        call_args = mock_logger.exception.call_args
        # First positional arg is the format string: "Error in %s"
        format_str = call_args[0][0]
        assert "Error in %s" in format_str or "Error in" in format_str
