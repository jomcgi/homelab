"""Shared fixtures for monolith e2e tests.

Manages a real PostgreSQL 16 + pgvector instance per test session,
with per-test SAVEPOINT rollback for isolation.
"""

from __future__ import annotations

import hashlib
import os
import random
import signal
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import event, text
from sqlmodel import Session, create_engine


def pytest_configure(config):
    """Set asyncio_mode so @pytest.mark.asyncio works without ini config."""
    config.option.asyncio_mode = "auto"


# ---------------------------------------------------------------------------
# Suppress env vars BEFORE importing app modules (module-level side effects)
# ---------------------------------------------------------------------------
os.environ.pop("STATIC_DIR", None)
os.environ.pop("DISCORD_BOT_TOKEN", None)
os.environ.pop("ICAL_FEED_URL", None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class PgInfo:
    """Connection info for the test PostgreSQL instance."""

    url: str
    port: int


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _find_pg_root() -> Path:
    """Locate the extracted PostgreSQL binaries from Bazel runfiles."""
    srcdir = os.environ.get("TEST_SRCDIR", "")
    candidates = [
        Path(srcdir) / "_main" / "external" / "postgres_test",
        Path(srcdir) / "postgres_test",
    ]
    for candidate in candidates:
        if (candidate / "bin" / "postgres").exists():
            return candidate
    raise FileNotFoundError(
        f"Could not find postgres_test binaries under TEST_SRCDIR={srcdir!r}. "
        f"Searched: {[str(c) for c in candidates]}"
    )


def _find_migrations_dir() -> Path:
    """Locate migration SQL files from Bazel runfiles."""
    srcdir = os.environ.get("TEST_SRCDIR", "")
    candidate = (
        Path(srcdir) / "_main" / "projects" / "monolith" / "chart" / "migrations"
    )
    if candidate.is_dir():
        return candidate
    raise FileNotFoundError(
        f"Could not find migrations dir at {candidate}. TEST_SRCDIR={srcdir!r}"
    )


# ---------------------------------------------------------------------------
# Session-scoped: real PostgreSQL
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def pg(tmp_path_factory):
    """Start a real PostgreSQL 16 + pgvector instance for the test session."""
    pg_root = _find_pg_root()
    pg_bin = pg_root / "bin"
    pg_lib = pg_root / "lib"
    pg_share = pg_root / "share"

    datadir = tmp_path_factory.mktemp("pgdata")
    port = _find_free_port()

    env = os.environ.copy()
    # Ensure PG can find its shared libraries
    existing_ld = env.get("LD_LIBRARY_PATH", "")
    env["LD_LIBRARY_PATH"] = f"{pg_lib}:{existing_ld}" if existing_ld else str(pg_lib)
    # macOS equivalent
    existing_dyld = env.get("DYLD_LIBRARY_PATH", "")
    env["DYLD_LIBRARY_PATH"] = (
        f"{pg_lib}:{existing_dyld}" if existing_dyld else str(pg_lib)
    )

    # --- initdb ---
    subprocess.run(
        [
            str(pg_bin / "initdb"),
            "-D",
            str(datadir),
            "--no-locale",
            "-U",
            "test",
        ],
        env=env,
        check=True,
        capture_output=True,
    )

    # --- start postgres ---
    proc = subprocess.Popen(
        [
            str(pg_bin / "postgres"),
            "-D",
            str(datadir),
            "-p",
            str(port),
            "-k",
            str(datadir),  # unix socket dir
            "-c",
            f"dynamic_library_path={pg_lib}",
            "-c",
            f"extension_dir={pg_share}/extension",
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # --- wait for ready ---
    pg_isready = pg_bin / "pg_isready"
    deadline = time.monotonic() + 6.0
    ready = False
    while time.monotonic() < deadline:
        result = subprocess.run(
            [str(pg_isready), "-h", "127.0.0.1", "-p", str(port), "-U", "test"],
            env=env,
            capture_output=True,
        )
        if result.returncode == 0:
            ready = True
            break
        time.sleep(0.2)

    if not ready:
        proc.terminate()
        proc.wait(timeout=5)
        stderr = proc.stderr.read().decode() if proc.stderr else ""
        raise RuntimeError(
            f"PostgreSQL failed to become ready within 6s on port {port}.\n"
            f"stderr: {stderr}"
        )

    # --- create database and install pgvector ---
    base_url = f"postgresql+psycopg://test@127.0.0.1:{port}"
    engine = create_engine(f"{base_url}/postgres")
    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")
        conn.execute(text("CREATE DATABASE monolith"))
    engine.dispose()

    monolith_url = f"{base_url}/monolith"
    engine = create_engine(monolith_url)
    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    engine.dispose()

    # --- apply migrations ---
    migrations_dir = _find_migrations_dir()
    sql_files = sorted(migrations_dir.glob("*.sql"))
    engine = create_engine(monolith_url)
    with engine.begin() as conn:
        for sql_file in sql_files:
            conn.execute(text(sql_file.read_text()))
    engine.dispose()

    yield PgInfo(url=monolith_url, port=port)

    # --- teardown ---
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


# ---------------------------------------------------------------------------
# Function-scoped: SAVEPOINT session
# ---------------------------------------------------------------------------


@pytest.fixture()
def session(pg):
    """Per-test session with SAVEPOINT rollback for isolation."""
    engine = create_engine(pg.url)
    conn = engine.connect()
    txn = conn.begin()
    conn.begin_nested()  # SAVEPOINT

    sess = Session(bind=conn)

    @event.listens_for(sess, "after_transaction_end")
    def restart_savepoint(session, transaction):
        if transaction.nested and not transaction._parent.nested:
            session.begin_nested()

    yield sess

    sess.close()
    txn.rollback()
    conn.close()
    engine.dispose()


# ---------------------------------------------------------------------------
# Function-scoped: FastAPI TestClient
# ---------------------------------------------------------------------------


def _make_create_task_patcher():
    """Return a side_effect function that closes coroutines instead of scheduling them."""

    def capture_create_task(coro, **kwargs):
        if hasattr(coro, "close"):
            coro.close()
        return MagicMock()

    return capture_create_task


@pytest.fixture()
def client(session):
    """TestClient with DB override, mocked vault, and suppressed background tasks."""
    from app.db import get_session  # noqa: E402
    from app.main import app  # noqa: E402

    def get_session_override():
        yield session

    app.dependency_overrides[get_session] = get_session_override

    mock_vault_response = MagicMock()
    mock_vault_response.json.return_value = {"id": "test-note"}
    mock_vault_response.raise_for_status = MagicMock()

    mock_async_client = AsyncMock()
    mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
    mock_async_client.__aexit__ = AsyncMock(return_value=None)
    mock_async_client.post = AsyncMock(return_value=mock_vault_response)

    with patch("asyncio.create_task", side_effect=_make_create_task_patcher()):
        with patch("notes.service.httpx.AsyncClient", return_value=mock_async_client):
            from fastapi.testclient import TestClient

            yield TestClient(app, raise_server_exceptions=False)

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Function-scoped: mock EmbeddingClient
# ---------------------------------------------------------------------------


def deterministic_embedding(text: str) -> list[float]:
    """Hash-based deterministic 1024-dim unit vector."""
    h = hashlib.sha256(text.encode()).digest()
    rng = random.Random(int.from_bytes(h[:8], "big"))
    vec = [rng.gauss(0, 1) for _ in range(1024)]
    norm = sum(x * x for x in vec) ** 0.5
    return [x / norm for x in vec]


@pytest.fixture()
def embed_client():
    """Mock EmbeddingClient with deterministic embeddings."""
    from chat.embedding import EmbeddingClient

    mock = MagicMock(spec=EmbeddingClient)
    mock.embed = AsyncMock(side_effect=deterministic_embedding)
    return mock


# ---------------------------------------------------------------------------
# Function-scoped: MessageStore
# ---------------------------------------------------------------------------


@pytest.fixture()
def store(session, embed_client):
    """MessageStore wired to the SAVEPOINT session and mock embeddings."""
    from chat.store import MessageStore

    return MessageStore(session=session, embed_client=embed_client)
