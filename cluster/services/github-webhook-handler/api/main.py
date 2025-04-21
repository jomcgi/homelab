"""Github Actions Healthcheck API"""

import logging

import structlog
import uvicorn
from fastapi import FastAPI

from health import HealthResponse, get_health
from instrumentation import _instrument, _configure_structlog
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from github_events import handle_events
from settings import HANDLER_SETTINGS

class HealthCheckFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return record.getMessage().find("/health") == -1

logging.getLogger("uvicorn.access").addFilter(
    HealthCheckFilter())

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
    endpoint=handle_events,
    methods=["POST"],
    status_code=200,
)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=HANDLER_SETTINGS.port)
