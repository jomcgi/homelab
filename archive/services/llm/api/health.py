from pydantic import BaseModel
import logging
import structlog

logging.basicConfig(level=logging.INFO)
logger = structlog.get_logger(__name__)


class HealthResponse(BaseModel):
    """Response class for health check"""

    OK: bool = True
    utils_health: dict[str, bool] | None = None


async def get_health():
    """Health check route"""
    logger.debug("Successful Health Check")
    return HealthResponse()
