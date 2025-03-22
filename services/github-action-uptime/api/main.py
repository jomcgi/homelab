"""Github Actions Healthcheck API"""

import logging

import structlog
import uvicorn
from fastapi import FastAPI

from health import HealthResponse, get_health
from instrumentation import _instrument, _configure_structlog
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from actions_uptime import uptime
from settings import GITHUB_UPTIME_SETTINGS

logging.basicConfig(level=logging.INFO)
logger = structlog.get_logger(__name__)

app = FastAPI()

app.add_api_route(
    path="/health",
    endpoint=get_health,
    methods=["GET"],
    status_code=200,
    response_model=HealthResponse,
)

app.add_api_route(
    path="/events",
    endpoint=uptime,
    methods=["POST"],
    status_code=200,
)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=GITHUB_UPTIME_SETTINGS.port)
