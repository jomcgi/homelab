"""
Error handling utilities for the find_good_hikes project.

This module provides consistent error handling patterns and graceful degradation
following the philosophy of "define errors out of existence" where possible.
"""

import logging
import sqlite3
import time
from collections.abc import Callable
from functools import wraps
from pathlib import Path
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class AppError(Exception):
    """Base exception for application errors."""

    def __init__(self, message: str, recoverable: bool = True):
        super().__init__(message)
        self.recoverable = recoverable


class DatabaseError(AppError):
    """Database-related errors."""

    pass


class NetworkError(AppError):
    """Network-related errors."""

    pass


class ConfigurationError(AppError):
    """Configuration-related errors."""

    def __init__(self, message: str):
        super().__init__(message, recoverable=False)


class DataValidationError(AppError):
    """Data validation errors."""

    pass


def retry_on_failure(
    max_retries: int = 3,
    delay: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: tuple = (Exception,),
):
    """
    Decorator to retry function calls on specific exceptions.

    Args:
        max_retries: Maximum number of retry attempts
        delay: Initial delay between retries in seconds
        backoff_factor: Multiplier for delay after each retry
        exceptions: Tuple of exceptions to catch and retry on
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception = None
            current_delay = delay

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_retries:
                        logger.error(
                            f"Function {func.__name__} failed after {max_retries} retries: {e}"
                        )
                        raise

                    logger.warning(
                        f"Function {func.__name__} failed (attempt {attempt + 1}/{max_retries + 1}): {e}"
                    )
                    if attempt < max_retries:
                        logger.debug(f"Retrying in {current_delay:.1f} seconds...")
                        time.sleep(current_delay)
                        current_delay *= backoff_factor

            # This should never be reached, but just in case
            raise last_exception

        return wrapper

    return decorator


def safe_database_operation(func: Callable[..., T]) -> Callable[..., T | None]:
    """
    Decorator for database operations that gracefully handles failures.

    Returns None on database errors instead of raising exceptions.
    """

    @wraps(func)
    def wrapper(*args, **kwargs) -> T | None:
        try:
            return func(*args, **kwargs)
        except sqlite3.Error as e:
            logger.error(f"Database error in {func.__name__}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in {func.__name__}: {e}")
            return None

    return wrapper


def ensure_directory_exists(path: Path) -> bool:
    """
    Ensure a directory exists, creating it if necessary.

    Returns True if directory exists or was created successfully.
    """
    try:
        path.mkdir(parents=True, exist_ok=True)
        return True
    except (OSError, PermissionError) as e:
        logger.error(f"Failed to create directory {path}: {e}")
        return False


def validate_database_file(db_path: str) -> bool:
    """
    Validate that a database file exists and is accessible.

    Returns True if database is accessible, False otherwise.
    """
    try:
        path = Path(db_path)
        if not path.exists():
            logger.warning(f"Database file does not exist: {db_path}")
            return False

        # Try to open the database to verify it's not corrupted
        with sqlite3.connect(db_path) as conn:
            conn.execute("SELECT 1")

        return True
    except sqlite3.Error as e:
        logger.error(f"Database validation failed for {db_path}: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error validating database {db_path}: {e}")
        return False


def graceful_shutdown(func: Callable[..., T]) -> Callable[..., T | None]:
    """
    Decorator that handles graceful shutdown on critical errors.

    Logs the error and returns None instead of crashing the application.
    """

    @wraps(func)
    def wrapper(*args, **kwargs) -> T | None:
        try:
            return func(*args, **kwargs)
        except KeyboardInterrupt:
            logger.info("Operation cancelled by user")
            return None
        except ConfigurationError as e:
            logger.error(f"Configuration error: {e}")
            logger.error("Please check your configuration and try again")
            return None
        except Exception as e:
            logger.error(f"Critical error in {func.__name__}: {e}")
            logger.error(
                "Application will continue but some functionality may be limited"
            )
            return None

    return wrapper


def handle_network_errors(func: Callable[..., T]) -> Callable[..., T | None]:
    """
    Decorator for network operations that handles common network failures.
    """

    @wraps(func)
    def wrapper(*args, **kwargs) -> T | None:
        try:
            return func(*args, **kwargs)
        except (ConnectionError, TimeoutError) as e:
            logger.warning(f"Network error in {func.__name__}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in {func.__name__}: {e}")
            return None

    return wrapper


def log_performance(func: Callable[..., T]) -> Callable[..., T]:
    """
    Decorator to log function performance for monitoring.
    """

    @wraps(func)
    def wrapper(*args, **kwargs) -> T:
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            duration = time.time() - start_time
            logger.debug(f"{func.__name__} completed in {duration:.2f} seconds")
            return result
        except Exception as e:
            duration = time.time() - start_time
            logger.warning(f"{func.__name__} failed after {duration:.2f} seconds: {e}")
            raise

    return wrapper


def safe_int_conversion(value: Any, default: int = 0) -> int:
    """
    Safely convert a value to integer, returning default on failure.
    """
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def safe_float_conversion(value: Any, default: float = 0.0) -> float:
    """
    Safely convert a value to float, returning default on failure.
    """
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def create_error_context(operation: str, **context) -> dict:
    """
    Create a consistent error context for logging.

    Args:
        operation: The operation being performed
        **context: Additional context information

    Returns:
        Dictionary with error context
    """
    return {"operation": operation, "timestamp": time.time(), **context}


class ErrorCollector:
    """
    Collect and report multiple non-critical errors.

    Useful for operations that should continue despite individual failures.
    """

    def __init__(self):
        self.errors = []

    def add_error(self, operation: str, error: Exception, **context):
        """Add an error to the collection."""
        error_info = {
            "operation": operation,
            "error": str(error),
            "error_type": type(error).__name__,
            "timestamp": time.time(),
            **context,
        }
        self.errors.append(error_info)
        logger.warning(f"Error in {operation}: {error}")

    def has_errors(self) -> bool:
        """Check if any errors were collected."""
        return len(self.errors) > 0

    def get_summary(self) -> str:
        """Get a summary of collected errors."""
        if not self.errors:
            return "No errors"

        error_counts = {}
        for error in self.errors:
            error_type = error["error_type"]
            error_counts[error_type] = error_counts.get(error_type, 0) + 1

        summary_parts = [
            f"{count} {error_type}" for error_type, count in error_counts.items()
        ]
        return f"Collected {len(self.errors)} errors: " + ", ".join(summary_parts)

    def log_summary(self):
        """Log a summary of all collected errors."""
        if not self.errors:
            logger.info("Operation completed without errors")
        else:
            logger.warning(self.get_summary())
            for error in self.errors:
                logger.debug(f"Error details: {error}")


def with_error_collection(
    func: Callable[..., T],
) -> Callable[..., tuple[T | None, ErrorCollector]]:
    """
    Decorator that provides an ErrorCollector to the function.

    Returns a tuple of (result, error_collector).
    """

    @wraps(func)
    def wrapper(*args, **kwargs) -> tuple[T | None, ErrorCollector]:
        error_collector = ErrorCollector()
        try:
            result = func(error_collector, *args, **kwargs)
            return result, error_collector
        except Exception as e:
            logger.exception("Error in %s", func.__name__)
            error_collector.add_error(func.__name__, e)
            return None, error_collector

    return wrapper
