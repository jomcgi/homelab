"""Grimoire Ingest Job.

Batch process (K8s Job) that:
1. Downloads a PDF from SeaweedFS (S3-compatible)
2. Extracts text per page using pymupdf4llm
3. Chunks text by content type (stat blocks, spells, rules)
4. Embeds each chunk via Gemini text-embedding-005
5. Publishes chunks with embeddings to NATS JetStream
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import tempfile
import time
from urllib.parse import urlparse

import boto3
import botocore.config
import nats
import pymupdf4llm
from google import genai
from google.genai import types as genai_types

from services.grimoire.ingest.chunker import Chunk, chunk_document

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("grimoire.ingest")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PDF_PATH = os.environ.get("PDF_PATH", "")  # e.g. s3://grimoire-sourcebooks/phb.pdf
SOURCE_BOOK = os.environ.get("SOURCE_BOOK", "")  # e.g. PHB
EDITION = os.environ.get("EDITION", "2024")
AUDIENCE = os.environ.get("AUDIENCE", "player_safe")
NATS_URL = os.environ.get("NATS_URL", "nats://nats.nats.svc.cluster.local:4222")
SEAWEEDFS_ENDPOINT = os.environ.get(
    "SEAWEEDFS_ENDPOINT",
    "http://seaweedfs-s3.seaweedfs.svc.cluster.local:8333",
)
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")

# Gemini embedding model and batch size.
EMBEDDING_MODEL = "text-embedding-005"
EMBEDDING_BATCH_SIZE = 100  # Gemini supports up to 100 texts per request.

# NATS JetStream stream and subject.
NATS_STREAM = "GRIMOIRE_CHUNKS"
NATS_SUBJECT_PREFIX = "grimoire.chunks"


# ---------------------------------------------------------------------------
# Step 1: Download PDF from SeaweedFS
# ---------------------------------------------------------------------------

def download_pdf(s3_uri: str, endpoint: str) -> str:
    """Download a PDF from an S3-compatible store and return the local path.

    Args:
        s3_uri: S3 URI like ``s3://bucket/key.pdf``.
        endpoint: The S3 endpoint URL.

    Returns:
        Path to the downloaded temporary file.
    """
    parsed = urlparse(s3_uri)
    bucket = parsed.netloc
    key = parsed.path.lstrip("/")

    if not bucket or not key:
        raise ValueError(f"Invalid S3 URI: {s3_uri!r}  (expected s3://bucket/key)")

    logger.info("Downloading %s from bucket=%s key=%s endpoint=%s", s3_uri, bucket, key, endpoint)

    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id="",
        aws_secret_access_key="",
        config=botocore.config.Config(signature_version=botocore.UNSIGNED),
    )

    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    try:
        s3.download_file(bucket, key, tmp.name)
    except Exception:
        os.unlink(tmp.name)
        raise

    logger.info("Downloaded PDF to %s", tmp.name)
    return tmp.name


# ---------------------------------------------------------------------------
# Step 2: Extract text from PDF
# ---------------------------------------------------------------------------

def extract_pages(pdf_path: str) -> list[tuple[int, str]]:
    """Extract markdown text from each page of a PDF.

    Returns a list of (1-based page_number, markdown_text) pairs.
    """
    logger.info("Extracting text from %s", pdf_path)

    # pymupdf4llm.to_markdown returns a single string by default.
    # With page_chunks=True it returns a list of dicts with keys
    # "metadata" (containing "page") and "text".
    page_chunks = pymupdf4llm.to_markdown(pdf_path, page_chunks=True)

    pages: list[tuple[int, str]] = []
    for chunk in page_chunks:
        page_num = chunk.get("metadata", {}).get("page", 0) + 1  # 0-indexed -> 1-indexed
        text = chunk.get("text", "")
        if text.strip():
            pages.append((page_num, text))

    logger.info("Extracted %d non-empty pages", len(pages))
    return pages


# ---------------------------------------------------------------------------
# Step 3: Embed chunks via Gemini
# ---------------------------------------------------------------------------

def create_genai_client() -> genai.Client:
    """Create a google-genai Client using API key or ADC."""
    if GOOGLE_API_KEY:
        return genai.Client(api_key=GOOGLE_API_KEY)
    return genai.Client()  # Falls back to Application Default Credentials


def embed_chunks(client: genai.Client, chunks: list[Chunk]) -> list[list[float]]:
    """Embed a list of chunks in batches, returning one embedding per chunk.

    Uses Gemini ``text-embedding-005`` which produces 768-dimensional vectors.
    """
    all_embeddings: list[list[float]] = []
    texts = [c.text for c in chunks]

    for i in range(0, len(texts), EMBEDDING_BATCH_SIZE):
        batch = texts[i : i + EMBEDDING_BATCH_SIZE]
        logger.info(
            "Embedding batch %d-%d of %d chunks",
            i + 1,
            min(i + len(batch), len(texts)),
            len(texts),
        )
        response = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=batch,
            config=genai_types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"),
        )
        for emb in response.embeddings:
            all_embeddings.append(emb.values)

        # Rate limit: Gemini embedding has 1500 RPM on free tier.
        if i + EMBEDDING_BATCH_SIZE < len(texts):
            time.sleep(0.5)

    return all_embeddings


# ---------------------------------------------------------------------------
# Step 4: Publish to NATS JetStream
# ---------------------------------------------------------------------------

def _build_message(chunk: Chunk, embedding: list[float]) -> bytes:
    """Serialize a chunk + embedding into the JSON format the chunk-writer expects."""
    payload = {
        "text": chunk.text,
        "embedding": embedding,
        "source_book": SOURCE_BOOK,
        "page": chunk.page,
        "section": chunk.section,
        "section_path": "",
        "content_type": chunk.content_type,
        "audience": AUDIENCE,
        "edition": EDITION,
        "metadata": {},
    }
    return json.dumps(payload).encode()


async def publish_to_nats(chunks: list[Chunk], embeddings: list[list[float]]) -> int:
    """Connect to NATS and publish each chunk to JetStream.

    Returns the number of successfully published messages.
    """
    logger.info("Connecting to NATS at %s", NATS_URL)
    nc = await nats.connect(NATS_URL)
    js = nc.jetstream()

    # Ensure the stream exists (the chunk-writer also creates it, but we
    # create it here too so the ingest job can run independently).
    try:
        await js.find_stream_name_by_subject(f"{NATS_SUBJECT_PREFIX}.>")
        logger.info("Stream %s already exists", NATS_STREAM)
    except nats.js.errors.NotFoundError:
        await js.add_stream(
            name=NATS_STREAM,
            subjects=[f"{NATS_SUBJECT_PREFIX}.>"],
            retention="limits",
            storage="file",
            num_replicas=1,
        )
        logger.info("Created stream %s", NATS_STREAM)

    subject = f"{NATS_SUBJECT_PREFIX}.{SOURCE_BOOK}"
    published = 0

    for chunk, embedding in zip(chunks, embeddings):
        data = _build_message(chunk, embedding)
        try:
            await js.publish(subject, data)
            published += 1
        except Exception as e:
            logger.error("Failed to publish chunk (page=%d, section=%s): %s", chunk.page, chunk.section, e)

    await nc.close()
    logger.info("Published %d/%d chunks to %s", published, len(chunks), subject)
    return published


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

async def run() -> None:
    """Execute the full ingest pipeline."""
    # Validate required config.
    if not PDF_PATH:
        logger.error("PDF_PATH environment variable is required")
        sys.exit(1)
    if not SOURCE_BOOK:
        logger.error("SOURCE_BOOK environment variable is required")
        sys.exit(1)

    logger.info(
        "Starting ingest: source_book=%s edition=%s audience=%s pdf=%s",
        SOURCE_BOOK,
        EDITION,
        AUDIENCE,
        PDF_PATH,
    )

    # 1. Download PDF from SeaweedFS.
    pdf_path = download_pdf(PDF_PATH, SEAWEEDFS_ENDPOINT)

    try:
        # 2. Extract markdown text per page.
        pages = extract_pages(pdf_path)
        if not pages:
            logger.error("No text extracted from PDF")
            sys.exit(1)

        # 3. Chunk the document.
        chunks = chunk_document(pages)
        logger.info("Created %d chunks from %d pages", len(chunks), len(pages))
        if not chunks:
            logger.error("No chunks produced")
            sys.exit(1)

        # Log content-type distribution.
        type_counts: dict[str, int] = {}
        for c in chunks:
            type_counts[c.content_type] = type_counts.get(c.content_type, 0) + 1
        logger.info("Chunk distribution: %s", type_counts)

        # 4. Embed chunks via Gemini.
        genai_client = create_genai_client()
        embeddings = embed_chunks(genai_client, chunks)
        if len(embeddings) != len(chunks):
            logger.error(
                "Embedding count mismatch: got %d embeddings for %d chunks",
                len(embeddings),
                len(chunks),
            )
            sys.exit(1)

        # 5. Publish to NATS JetStream.
        published = await publish_to_nats(chunks, embeddings)
        logger.info(
            "Ingest complete: %d chunks published for %s",
            published,
            SOURCE_BOOK,
        )

    finally:
        # Clean up the temporary PDF file.
        if os.path.exists(pdf_path):
            os.unlink(pdf_path)
            logger.info("Cleaned up temporary file %s", pdf_path)


def main() -> None:
    """Entry point."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
