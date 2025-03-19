"""LLM API"""

import logging

import structlog
import uvicorn
from fastapi import FastAPI

from instrumentation import _instrument
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from api.claude import anthropic_inference

from api.google import google_inference
from api.health import HealthResponse, get_health
from api.log_config import configure_structlog
from api.types import LLMResponse

logging.basicConfig(level=logging.INFO)
logger = structlog.get_logger(__name__)


app = FastAPI(
    on_startup=[_instrument, configure_structlog],
)
FastAPIInstrumentor.instrument_app(app, excluded_urls="health")


app.add_api_route(
    path="/health",
    endpoint=get_health,
    methods=["GET"],
    status_code=200,
    response_model=HealthResponse,
)

app.add_api_route(
    path="/infer/gemini",
    endpoint=google_inference,
    methods=["POST"],
    status_code=200,
    response_model=LLMResponse,
)

app.add_api_route(
    path="/infer/anthropic",
    endpoint=anthropic_inference,
    methods=["POST"],
    status_code=200,
    response_model=LLMResponse,
)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9090)
