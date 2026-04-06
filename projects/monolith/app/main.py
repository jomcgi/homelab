from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.log import configure_logging
from home.router import router as home_router
from home.scheduler import run_scheduler
from notes.router import router as notes_router
from chat.router import router as chat_router
from shared.router import router as schedule_router

configure_logging()
logger = logging.getLogger(__name__)


async def _wait_for_sidecar() -> None:
    """Block until the frontend sidecar is healthy, or return immediately if unconfigured."""
    url = os.environ.get("FRONTEND_HEALTH_URL", "")
    if not url:
        return
    import httpx

    logger.info("Waiting for frontend sidecar at %s", url)
    async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
        while True:
            try:
                resp = await client.get(url, timeout=2)
                if resp.status_code < 500:
                    logger.info("Frontend sidecar is ready")
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(2)


def _log_task_exception(task: "asyncio.Task[object]") -> None:
    """Log unhandled exceptions from background tasks instead of silently dropping them."""
    if not task.cancelled() and task.exception():
        logger.error(
            "Background task %s failed", task.get_name(), exc_info=task.exception()
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    from shared.service import poll_calendar

    # Initial fetch, then poll every 5 minutes
    async def calendar_loop():
        while True:
            await poll_calendar()
            await asyncio.sleep(300)

    scheduler_task = asyncio.create_task(run_scheduler())
    calendar_task = asyncio.create_task(calendar_loop())

    app.state.bot = None
    app.state.backfill_task = None

    # Start Discord bot if token is configured
    bot = None
    bot_task = None
    discord_token = os.environ.get("DISCORD_BOT_TOKEN", "")
    if discord_token:
        from chat.bot import create_bot

        bot = create_bot()
        app.state.bot = bot

        async def _start_bot_when_ready():
            await _wait_for_sidecar()
            await bot.start(discord_token)

        bot_task = asyncio.create_task(_start_bot_when_ready())
        bot_task.add_done_callback(_log_task_exception)
        logger.info("Discord bot starting")

    # Start summary loop if chat is enabled
    summary_task = None
    if discord_token:

        async def _summary_loop():
            from chat.models import ChannelSummary, UserChannelSummary
            from chat.summarizer import (
                build_llm_caller,
                generate_channel_summaries,
                generate_summaries,
            )

            stale_threshold = 86400  # 24 hours in seconds

            while True:
                # Check if summaries need generating (missing or stale)
                try:
                    with Session(get_engine()) as session:
                        from sqlmodel import select

                        latest_user = session.exec(
                            select(UserChannelSummary.updated_at)
                            .order_by(UserChannelSummary.updated_at.desc())
                            .limit(1)
                        ).first()
                        latest_channel = session.exec(
                            select(ChannelSummary.updated_at)
                            .order_by(ChannelSummary.updated_at.desc())
                            .limit(1)
                        ).first()

                    now = datetime.now(timezone.utc)
                    needs_run = True
                    if latest_user and latest_channel:
                        newest = max(latest_user, latest_channel)
                        age = (now - newest).total_seconds()
                        needs_run = age >= stale_threshold

                    if needs_run:
                        logger.info("Running summary generation (stale or missing)")
                        with Session(get_engine()) as session:
                            llm_caller = build_llm_caller()
                            await generate_summaries(session, llm_caller)
                            await generate_channel_summaries(session, llm_caller)
                        logger.info("Summary generation complete")
                except Exception:
                    logger.exception("Summary generation failed")

                await asyncio.sleep(stale_threshold)

        from app.db import get_engine
        from sqlmodel import Session

        summary_task = asyncio.create_task(_summary_loop())
        summary_task.add_done_callback(_log_task_exception)
        logger.info("Summary loop started (24h interval)")

    # Sweep for expired message locks and clean up old completed ones
    sweep_task = None
    if discord_token and bot:

        async def _lock_sweep_loop():
            from chat.embedding import EmbeddingClient
            from chat.store import MessageStore

            embed_client = EmbeddingClient()
            # Wait for bot to connect before sweeping
            await bot.wait_until_ready()
            while True:
                await asyncio.sleep(30)
                try:
                    with Session(get_engine()) as session:
                        store = MessageStore(session=session, embed_client=embed_client)
                        expired = store.reclaim_expired(ttl_seconds=30, limit=5)
                        for lock in expired:
                            logger.info(
                                "Reclaiming expired lock for message %s",
                                lock.discord_message_id,
                            )
                            await bot.reprocess_message(
                                lock.discord_message_id, lock.channel_id
                            )
                        cleaned = store.cleanup_completed(max_age_seconds=3600)
                        if cleaned:
                            logger.debug("Cleaned up %d completed locks", cleaned)
                except Exception:
                    logger.exception("Lock sweep failed")

        sweep_task = asyncio.create_task(_lock_sweep_loop())
        sweep_task.add_done_callback(_log_task_exception)
        logger.info("Message lock sweep started (30s interval)")

    logger.info("Monolith started")
    yield
    backfill_task = getattr(app.state, "backfill_task", None)
    if backfill_task and not backfill_task.done():
        backfill_task.cancel()
    if sweep_task:
        sweep_task.cancel()
    if summary_task:
        summary_task.cancel()
    if bot:
        await bot.close()
    if bot_task:
        bot_task.cancel()
    calendar_task.cancel()
    scheduler_task.cancel()
    logger.info("Monolith shutting down")


app = FastAPI(title="Monolith", lifespan=lifespan)

app.include_router(home_router)
app.include_router(schedule_router)
app.include_router(notes_router)
app.include_router(chat_router)


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

# OTEL instrumentation (manual setup -- operator auto-inject breaks Bazel runfiles)
try:
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create({"service.name": "monolith-backend"})
    exporter = OTLPSpanExporter(
        endpoint=os.environ.get(
            "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
            "http://signoz-k8s-infra-otel-agent.signoz.svc.cluster.local:4318/v1/traces",
        ),
    )
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(exporter))

    from opentelemetry import trace

    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
    logger.info("OpenTelemetry instrumentation enabled")
except ImportError:
    logger.info("OpenTelemetry not available, skipping instrumentation")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
