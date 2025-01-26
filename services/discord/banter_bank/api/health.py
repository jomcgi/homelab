from collections.abc import Iterable
from pydantic import BaseModel
import logging
import structlog
from fastapi import Response
from services.discord.shared.health_protocol import Healthable
from sqlalchemy.ext.asyncio import AsyncEngine

logging.basicConfig(level=logging.INFO)
logger = structlog.get_logger(__name__)


class HealthResponse(BaseModel):
    """Response class for health check"""

    OK: bool = True
    utils_health: dict[str, bool] | None = None


class PostgresConnection(Healthable):

    def __init__(self, engine: AsyncEngine):
        self.engine = engine

    async def is_healthy(self) -> bool:
        try:
            async with self.engine.connect() as conn:
                await conn.execute("SELECT 1")
                return True
        except Exception as e:
            logger.error("Failed to connect to postgres", error=str(e))
            return False


def create_health_coroutine(health_utils: Iterable[Healthable] | None = None):

    async def get_health(response: Response):  # type: ignore
        healthy_responses: dict[str, bool] = {}
        if health_utils:
            for health_util in health_utils:
                health_status = await health_util.is_healthy()
                healthy_responses[health_util.__class__.__name__] = health_status

            if not all(healthy_responses.values()):
                response.status_code = 503
                return HealthResponse(OK=False, utils_health=healthy_responses)

            return HealthResponse(utils_health=healthy_responses)

        return HealthResponse()

    return get_health
