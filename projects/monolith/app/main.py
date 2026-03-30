import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from schedule.router import router as schedule_router
from todo.router import router as todo_router
from todo.scheduler import run_scheduler

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio

    from schedule.service import poll_calendar

    # Initial fetch, then poll every 5 minutes
    async def calendar_loop():
        while True:
            await poll_calendar()
            await asyncio.sleep(300)

    scheduler_task = asyncio.create_task(run_scheduler())
    calendar_task = asyncio.create_task(calendar_loop())
    logger.info("Monolith started")
    yield
    calendar_task.cancel()
    scheduler_task.cancel()
    logger.info("Monolith shutting down")


app = FastAPI(title="Monolith", lifespan=lifespan)

app.include_router(todo_router)
app.include_router(schedule_router)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


# Serve SvelteKit static frontend (must be after API routes)
_static_dir = os.environ.get(
    "STATIC_DIR",
    str(Path(__file__).resolve().parent.parent / "frontend" / "dist"),
)
if Path(_static_dir).is_dir():
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="frontend")
    logger.info("Serving frontend from %s", _static_dir)

# OTEL instrumentation (optional -- enabled by auto-instrumentation annotation)
try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app)
    logger.info("OpenTelemetry instrumentation enabled")
except ImportError:
    logger.info("OpenTelemetry not available, skipping instrumentation")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
