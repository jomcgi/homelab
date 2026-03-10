"""MCP server for knowledge graph search."""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel

from projects.agent_platform.knowledge_graph.app.config import McpSettings
from projects.agent_platform.knowledge_graph.app.embedders.gemini import GeminiEmbedder
from projects.agent_platform.knowledge_graph.app.embedders.ollama import OllamaEmbedder
from projects.agent_platform.knowledge_graph.app.qdrant_client import QdrantClient
from projects.agent_platform.knowledge_graph.app.storage import S3Storage
from projects.agent_platform.knowledge_graph.app.telemetry import setup_telemetry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

settings = McpSettings()
qdrant: QdrantClient | None = None
storage: S3Storage | None = None
embedder = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global qdrant, storage, embedder

    setup_telemetry("knowledge-graph-mcp")

    qdrant = QdrantClient(
        url=settings.qdrant_url, collection=settings.qdrant_collection
    )
    storage = S3Storage(
        endpoint=settings.s3_endpoint,
        bucket=settings.s3_bucket,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
    )

    if settings.provider == "gemini":
        embedder = GeminiEmbedder(
            api_key=settings.gemini_api_key, model=settings.gemini_model
        )
    else:
        embedder = OllamaEmbedder(url=settings.ollama_url, model=settings.ollama_model)

    yield


app = FastAPI(title="Knowledge Graph MCP Server", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


class SearchRequest(BaseModel):
    query: str
    limit: int = 5


class SearchResult(BaseModel):
    score: float
    title: str
    source_url: str
    source_type: str
    section_header: str
    chunk_text: str
    content_hash: str
    chunk_index: int


@app.post("/tools/search_knowledge")
async def search_knowledge(req: SearchRequest):
    """Semantic search across the knowledge base."""
    query_vector = await embedder.embed_query(req.query)
    results = await qdrant.search(query_vector, limit=req.limit)
    return {
        "results": [
            SearchResult(
                score=r.get("score", 0),
                title=r.get("title", ""),
                source_url=r.get("source_url", ""),
                source_type=r.get("source_type", ""),
                section_header=r.get("section_header", ""),
                chunk_text=r.get("chunk_text", ""),
                content_hash=r.get("content_hash", ""),
                chunk_index=r.get("chunk_index", 0),
            )
            for r in results
        ]
    }


@app.post("/tools/get_source")
async def get_source(content_hash: str):
    """Retrieve full markdown source by content hash."""
    content = storage.get_content(content_hash)
    meta = storage.get_meta(content_hash)
    if not content:
        return {"error": "Not found"}
    return {"content": content, "meta": meta}


def main():
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=settings.port)


if __name__ == "__main__":
    main()
