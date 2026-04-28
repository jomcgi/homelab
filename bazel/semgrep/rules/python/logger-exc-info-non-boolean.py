# Tests for logger-exc-info-non-boolean rule.
import logging

logger = logging.getLogger(__name__)


# ruleid: logger-exc-info-non-boolean
logger.warning("Node resource aggregation failed: %s", resources, exc_info=resources)

# ruleid: logger-exc-info-non-boolean
logger.error("request failed", exc_info=exc)

# ruleid: logger-exc-info-non-boolean
logger.info("unexpected result", exc_info=some_dict)

# ruleid: logger-exc-info-non-boolean
logger.debug("context", exc_info=my_var)

# ruleid: logger-exc-info-non-boolean
logger.critical("fatal error", exc_info=err_obj)

# ruleid: logger-exc-info-non-boolean
logging.warning("msg", exc_info=some_var)

# ruleid: logger-exc-info-non-boolean
logging.error("something went wrong", exc_info=e)

# ok: exc_info=True is the correct pattern inside an except block
logger.warning("aggregation failed", exc_info=True)

# ok: exc_info=False explicitly suppresses traceback output
logger.error("suppressed traceback", exc_info=False)

# ok: no exc_info kwarg — not flagged
logger.warning("plain warning message")

# ok: exc_info=True via the logging module directly
logging.error("module-level error", exc_info=True)

# ok: exc_info=False via the logging module directly
logging.warning("module-level no trace", exc_info=False)

# ok: logger.exception always attaches traceback; no exc_info needed
logger.exception("unhandled exception")
