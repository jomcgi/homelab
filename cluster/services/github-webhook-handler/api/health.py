from pydantic import BaseModel
import logging

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


class HealthResponse(BaseModel):
    """Response class for health check"""

    OK: bool = True
    utils_health: dict[str, bool] | None = None


async def get_health():
    """Health check route"""
    logger.debug("Successful Health Check")
    return HealthResponse()
