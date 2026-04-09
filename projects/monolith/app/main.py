from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.log import configure_logging
from home.router import router as home_router
from notes.router import router as notes_router
from chat.router import router as chat_router
from shared.router import router as schedule_router

configure_logging()
logger = logging.getLogger("monolith.main")


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


async def _wait_for_vault_sync() -> None:
    """Block until the Obsidian vault volume contains at least one markdown file.

    The vault is an emptyDir populated asynchronously by the headless-sync
    sidecar. The sidecar's /tmp/ready signal is in its own container filesystem
    and cannot be read here; instead we poll the shared volume directly.

    Returns immediately if VAULT_ROOT does not exist (knowledge not configured).
    Times out after 5 minutes and proceeds with a warning so a sync failure
    does not permanently stall the app.
    """
    vault_root = Path(os.environ.get("VAULT_ROOT", "/vault"))
    if not vault_root.exists():
        return
    logger.info("Waiting for Obsidian vault sync at %s", vault_root)
    for _ in range(60):  # 60 × 5 s = 5-minute cap
        if any(vault_root.rglob("*.md")):
            logger.info("Vault sync ready")
            return
        await asyncio.sleep(5)
    logger.warning(
        "Vault sync wait timed out after 5 minutes; proceeding with empty vault"
    )


def _log_task_exception(task: "asyncio.Task[object]") -> None:
    """Log unhandled exceptions from background tasks instead of silently dropping them."""
    if not task.cancelled() and task.exception():
        logger.error(
            "Background task %s failed", task.get_name(), exc_info=task.exception()
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.db import get_engine
    from shared.scheduler import run_scheduler_loop
    from sqlmodel import Session

    app.state.bot = None
    app.state.backfill_task = None

    # Register all scheduled jobs
    with Session(get_engine()) as session:
        from home.service import on_startup as home_startup
        from knowledge.service import on_startup as knowledge_startup
        from shared.service import on_startup as shared_startup

        home_startup(session)
        knowledge_startup(session)
        shared_startup(session)

    # Start Discord bot + chat jobs if configured
    bot = None
    bot_task = None
    discord_token = os.environ.get("DISCORD_BOT_TOKEN", "")
    if discord_token:
        from chat.bot import create_bot
        from chat.summarizer import build_llm_caller
        from chat.summarizer import on_startup as chat_startup

        bot = create_bot()
        app.state.bot = bot

        with Session(get_engine()) as session:
            chat_startup(session, bot=bot, llm_call=build_llm_caller())

        async def _start_bot_when_ready():
            await _wait_for_sidecar()
            await bot.start(discord_token)

        bot_task = asyncio.create_task(_start_bot_when_ready())
        bot_task.add_done_callback(_log_task_exception)
        logger.info("Discord bot starting")

    # Wait for Obsidian vault sync before starting the scheduler so the
    # reconciler never sees an empty vault and prunes the DB on pod restart.
    await _wait_for_vault_sync()

    # Start the shared scheduler loop (replaces 4 separate asyncio tasks)
    scheduler_task = asyncio.create_task(run_scheduler_loop())
    scheduler_task.add_done_callback(_log_task_exception)

    # Lock sweep stays in-memory (30s, bot-coupled, already multi-pod safe via SKIP LOCKED)
    sweep_task = None
    if discord_token and bot:

        async def _lock_sweep_loop():
            from shared.embedding import EmbeddingClient
            from chat.store import MessageStore

            embed_client = EmbeddingClient()
            while not bot.is_ready():
                await asyncio.sleep(2)
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
    if bot:
        await bot.close()
    if bot_task:
        bot_task.cancel()
    scheduler_task.cancel()
    if _tracer_provider is not None:
        _tracer_provider.shutdown()
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
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

_tracer_provider = TracerProvider(
    resource=Resource.create({"service.name": "monolith-backend"}),
)
_tracer_provider.add_span_processor(
    BatchSpanProcessor(
        OTLPSpanExporter(
            endpoint=os.environ.get(
                "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
                "http://signoz-k8s-infra-otel-agent.signoz.svc.cluster.local:4318/v1/traces",
            ),
        )
    )
)
trace.set_tracer_provider(_tracer_provider)
FastAPIInstrumentor.instrument_app(app)
logger.info("OpenTelemetry instrumentation enabled")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")
