# Tests for no-print-in-service rule.
# Semgrep test annotations: `ruleid:` marks a line that SHOULD match;
# `ok:` marks a line that should NOT match.

import logging

logger = logging.getLogger(__name__)

# ruleid: no-print-in-service
print("starting service")

# ruleid: no-print-in-service
print(f"received message: {'hello'}")

# ok: using the logging module is correct
logger.info("starting service")

# ok: logger.warning is fine
logger.warning("degraded mode")

# ok: logger.error is fine
logger.error("failed to connect: %s", "timeout")
