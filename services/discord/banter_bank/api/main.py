"""Banter Bank API"""

import logging

import structlog
import uvicorn
from fastapi import FastAPI

from services.discord.banter_bank.api.instrumentation import _instrument
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from services.discord.banter_bank.api.log_config import configure_structlog
from services.discord.banter_bank.api.health import (
    PostgresConnection,
    create_health_coroutine,
    HealthResponse,
)
from services.discord.banter_bank.api.postgres import async_engine

logging.basicConfig(level=logging.INFO)
logger = structlog.get_logger(__name__)


app = FastAPI(
    on_startup=[_instrument, configure_structlog],
)
FastAPIInstrumentor.instrument_app(app, excluded_urls="health")


app.add_api_route(
    path="/health",
    endpoint=create_health_coroutine(
        [
            PostgresConnection(async_engine),
        ]
    ),
    methods=["GET"],
    status_code=200,
    response_model=HealthResponse,
)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9090)
