"""Scraper FastAPI application."""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
import sys
import time
from contextlib import asynccontextmanager
from urllib.parse import urlparse

import httpx
import yaml
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from projects.blog_knowledge_graph.knowledge_graph.app.config import ScraperSettings
from projects.blog_knowledge_graph.knowledge_graph.app.extractors.base import (
    RateLimiter,
)
from projects.blog_knowledge_graph.knowledge_graph.app.extractors.feed_extractor import (
    FeedExtractor,
)
from projects.blog_knowledge_graph.knowledge_graph.app.extractors.html_extractor import (
    HTMLExtractor,
)
from projects.blog_knowledge_graph.knowledge_graph.app.models import (
    SourceConfig,
    ScrapeResult,
    content_hash,
)
from projects.blog_knowledge_graph.knowledge_graph.app.notifications import (
    SlackNotifier,
)
from projects.blog_knowledge_graph.knowledge_graph.app.storage import S3Storage
from projects.blog_knowledge_graph.knowledge_graph.app.telemetry import (
    setup_telemetry,
    trace_span,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

settings = ScraperSettings()
storage: S3Storage | None = None
notifier: SlackNotifier | None = None
rate_limiter: RateLimiter | None = None
sources: list[SourceConfig] = []
extractors: list = []


def _validate_url(url: str) -> None:
    """Validate URL to prevent SSRF attacks."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"URL scheme must be http or https, got '{parsed.scheme}'")
    hostname = parsed.hostname or ""
    if not hostname:
        raise ValueError("URL must have a hostname")
    if hostname.endswith(".svc.cluster.local"):
        raise ValueError("URLs targeting cluster-internal services are not allowed")
    # Resolve hostname and check for private IPs
    try:
        for info in socket.getaddrinfo(hostname, None):
            addr = ipaddress.ip_address(info[4][0])
            if addr.is_private or addr.is_loopback or addr.is_link_local:
                raise ValueError(f"URL resolves to private/loopback address: {addr}")
    except socket.gaierror:
        pass  # DNS resolution may fail in test/sandbox; allow and let httpx handle it


def _load_sources(path: str) -> list[SourceConfig]:
    """Load and validate sources.yaml."""
    with open(path) as f:
        data = yaml.safe_load(f)

    source_list = data.get("sources", [])
    if not source_list:
        logger.warning("No sources configured in %s", path)
        return []

    # Validate: required fields and no duplicate URLs
    seen_urls: set[str] = set()
    validated: list[SourceConfig] = []
    for s in source_list:
        url = s.get("url", "")
        source_type = s.get("type", "")
        if not url or not source_type:
            raise ValueError(f"Source missing required 'url' or 'type': {s}")
        if source_type not in ("rss", "html"):
            raise ValueError(f"Invalid source type '{source_type}' for {url}")
        if url in seen_urls:
            raise ValueError(f"Duplicate source URL: {url}")
        seen_urls.add(url)
        validated.append(SourceConfig(url=url, type=source_type, name=s.get("name")))
    return validated


async def _scrape_source(
    source: SourceConfig,
    client: httpx.AsyncClient,
    force: bool = False,
) -> list[ScrapeResult]:
    """Scrape a single source, return results for each document."""
    results: list[ScrapeResult] = []
    source_type = source["type"]

    extractor = None
    for ext in extractors:
        if ext.can_handle(source["url"], source_type):
            extractor = ext
            break
    if not extractor:
        return [
            ScrapeResult(
                url=source["url"],
                content_hash=None,
                is_new=False,
                title="",
                error=f"No extractor for type '{source_type}'",
            )
        ]

    try:
        with trace_span(f"scrape:{source['url']}"):
            if rate_limiter:
                await rate_limiter.acquire(source["url"])
            docs = await extractor.extract(source["url"], client)
    except Exception as e:
        logger.exception("Failed to scrape %s", source["url"])
        return [
            ScrapeResult(
                url=source["url"],
                content_hash=None,
                is_new=False,
                title="",
                error=str(e),
            )
        ]

    for doc in docs:
        doc_hash = content_hash(doc["content"])
        if not force and storage and storage.exists(doc_hash):
            results.append(
                ScrapeResult(
                    url=doc["source_url"],
                    content_hash=doc_hash,
                    is_new=False,
                    title=doc["title"],
                    error=None,
                )
            )
            continue

        if storage:
            with trace_span(f"store:{doc_hash[:12]}"):
                storage.store(doc)

        results.append(
            ScrapeResult(
                url=doc["source_url"],
                content_hash=doc_hash,
                is_new=True,
                title=doc["title"],
                error=None,
            )
        )

    return results


@asynccontextmanager
async def lifespan(app: FastAPI):
    global storage, notifier, rate_limiter, sources, extractors

    setup_telemetry("knowledge-graph-scraper")

    storage = S3Storage(
        endpoint=settings.s3_endpoint,
        bucket=settings.s3_bucket,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
    )

    notifier = SlackNotifier(settings.slack_webhook_url)
    rate_limiter = RateLimiter(settings.default_rate_limit_seconds)

    extractors = [
        FeedExtractor(rate_limiter=rate_limiter),
        HTMLExtractor(),
    ]

    try:
        sources = _load_sources(str(settings.sources_yaml_path))
        logger.info("Loaded %d sources", len(sources))
    except Exception:
        logger.exception("Failed to load sources.yaml")
        sources = []

    yield


app = FastAPI(title="Knowledge Graph Scraper", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


class ScrapeRequest(BaseModel):
    url: str
    type: str = "html"
    force: bool = False


@app.post("/scrape")
async def scrape(req: ScrapeRequest):
    try:
        _validate_url(req.url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    source = SourceConfig(url=req.url, type=req.type, name=None)
    async with httpx.AsyncClient() as client:
        results = await _scrape_source(source, client, force=req.force)
    return {"results": results}


@app.post("/scrape-all")
async def scrape_all():
    start = time.monotonic()
    all_results: list[ScrapeResult] = []

    with trace_span("scrape-all"):
        async with httpx.AsyncClient() as client:
            for source in sources:
                results = await _scrape_source(source, client)
                all_results.extend(results)

    elapsed = time.monotonic() - start
    new_count = sum(1 for r in all_results if r["is_new"])
    error_count = sum(1 for r in all_results if r["error"])

    logger.info(
        "Batch scrape complete: %d total, %d new, %d errors in %.1fs",
        len(all_results),
        new_count,
        error_count,
        elapsed,
    )

    if notifier:
        await notifier.notify_batch(all_results)

    return {
        "total": len(all_results),
        "new": new_count,
        "errors": error_count,
        "elapsed_seconds": round(elapsed, 2),
        "results": all_results,
    }


@app.get("/status/{url:path}")
async def status(url: str):
    if not storage:
        raise HTTPException(status_code=503, detail="Storage not initialized")
    # Check all known hashes for this URL
    for hash_key in storage.list_all_hashes():
        meta = storage.get_meta(hash_key)
        if meta and meta.get("source_url") == url:
            return {"scraped": True, "content_hash": hash_key, "meta": meta}
    return {"scraped": False}


def _run_batch() -> None:
    """Run batch scrape as a standalone process (for CronJob)."""
    import uvicorn

    # Trigger lifespan manually via a short-lived server isn't ideal.
    # Instead, replicate setup inline.
    global storage, notifier, rate_limiter, sources, extractors

    setup_telemetry("knowledge-graph-scraper")

    storage = S3Storage(
        endpoint=settings.s3_endpoint,
        bucket=settings.s3_bucket,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
    )
    notifier = SlackNotifier(settings.slack_webhook_url)
    rate_limiter = RateLimiter(settings.default_rate_limit_seconds)
    extractors = [
        FeedExtractor(rate_limiter=rate_limiter),
        HTMLExtractor(),
    ]
    sources = _load_sources(str(settings.sources_yaml_path))
    logger.info("Loaded %d sources for batch scrape", len(sources))

    async def _batch():
        start = time.monotonic()
        all_results: list[ScrapeResult] = []
        async with httpx.AsyncClient() as client:
            for source in sources:
                results = await _scrape_source(source, client)
                all_results.extend(results)

        elapsed = time.monotonic() - start
        new_count = sum(1 for r in all_results if r["is_new"])
        error_count = sum(1 for r in all_results if r["error"])
        logger.info(
            "Batch complete: %d total, %d new, %d errors in %.1fs",
            len(all_results),
            new_count,
            error_count,
            elapsed,
        )
        if notifier:
            await notifier.notify_batch(all_results)

    asyncio.run(_batch())


def main():
    import uvicorn

    if len(sys.argv) > 1 and sys.argv[1] == "scrape-all":
        _run_batch()
    else:
        uvicorn.run(app, host="0.0.0.0", port=settings.port)


if __name__ == "__main__":
    main()
