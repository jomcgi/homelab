"""Shared structured logging configuration for the monolith backend."""

import logging
import sys


def configure_logging(level: int = logging.INFO) -> None:
    """Configure the root logger with a structured format.

    Call once at startup (before any getLogger calls emit) so every
    module that uses ``logging.getLogger(__name__)`` inherits a
    handler and level automatically.
    """
    logging.basicConfig(
        level=level,
        stream=sys.stdout,
        format="%(levelname)s %(name)s: %(message)s",
        force=True,
    )
    # Quiet noisy libraries
    logging.getLogger("discord.gateway").setLevel(logging.WARNING)
    logging.getLogger("discord.client").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
