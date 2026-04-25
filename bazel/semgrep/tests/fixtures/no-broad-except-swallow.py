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


# --- unbound except Exception: (no "as e") ---


# ruleid: no-broad-except-swallow
def bad_unbound_swallow():
    try:
        risky_operation()
    except Exception:
        pass  # silent failure, no binding!


# ruleid: no-broad-except-swallow
def bad_unbound_return_none():
    try:
        risky_operation()
    except Exception:
        return None  # hides the error


# ok: re-raises (unbound form)
def ok_unbound_reraise():
    try:
        risky_operation()
    except Exception:
        raise


# ok: logs with logger (unbound form)
def ok_unbound_log():
    try:
        risky_operation()
    except Exception:
        logger.exception("unexpected error in risky_operation")


# ok: logs with logging module (unbound form)
def ok_unbound_logging():
    try:
        risky_operation()
    except Exception:
        logging.warning("risky_operation failed")


def risky_operation():
    pass
