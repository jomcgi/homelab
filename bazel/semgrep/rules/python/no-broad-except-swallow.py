# Tests for no-broad-except-swallow rule.
import logging

logger = logging.getLogger(__name__)


# ruleid: no-broad-except-swallow
def bad_swallow():
    try:
        risky_operation()
    except Exception as e:
        pass  # silent failure!


# ruleid: no-broad-except-swallow
def bad_return_none():
    try:
        risky_operation()
    except Exception as e:
        return None  # hides the error


# ok: logs the exception
def ok_with_log():
    try:
        risky_operation()
    except Exception as e:
        logger.error("risky_operation failed: %s", e)


# ok: re-raises
def ok_reraise():
    try:
        risky_operation()
    except Exception as e:
        raise


# ok: re-raises the caught exception
def ok_reraise_e():
    try:
        risky_operation()
    except Exception as e:
        raise e


# ok: logs then re-raises
def ok_log_and_reraise():
    try:
        risky_operation()
    except Exception as e:
        logger.exception("unexpected error")
        raise


def risky_operation():
    pass
