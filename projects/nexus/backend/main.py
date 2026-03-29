import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .todo.router import router as todo_router
from .todo.scheduler import run_scheduler

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio

    scheduler_task = asyncio.create_task(run_scheduler())
    logger.info("Nexus started")
    yield
    scheduler_task.cancel()
    logger.info("Nexus shutting down")


app = FastAPI(title="Nexus", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(todo_router)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


# OTEL instrumentation (optional -- enabled by auto-instrumentation annotation)
try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app)
    logger.info("OpenTelemetry instrumentation enabled")
except ImportError:
    logger.info("OpenTelemetry not available, skipping instrumentation")
