"""
Shared fixtures and helpers for Bosun integration tests.

Converts fixture JSON files into JSONL lines, mocks
``asyncio.create_subprocess_exec`` with a ``MockProcess``, and provides
WebSocket message collection utilities.

This is a pytest conftest — fixtures are auto-discovered by tests
in this directory without explicit imports.
"""

import asyncio
import json
import sqlite3
from pathlib import Path
from unittest.mock import patch, AsyncMock

import pytest

import charts.bosun.backend.server as server

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ── Fixture → JSONL conversion ────────────────────────────────────────────


def _fixture_to_jsonl(desc: dict) -> str:
    """Convert a fixture JSON dict (with ``kind``) into a CLI JSONL line."""
    kind = desc["kind"]

    if kind == "system_init":
        return json.dumps(
            {
                "type": "system",
                "subtype": "init",
                "session_id": desc["data"].get("session_id", ""),
            }
        )

    if kind == "stream_event":
        return json.dumps(
            {
                "type": "stream_event",
                "event": desc["event"],
                "parent_tool_use_id": desc.get("parent_tool_use_id"),
            }
        )

    if kind == "assistant":
        return json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": desc["content"],
                    "model": desc.get("model", "claude-sonnet-4-5-20250929"),
                },
                "parent_tool_use_id": desc.get("parent_tool_use_id"),
            }
        )

    if kind == "result":
        return json.dumps(
            {
                "type": "result",
                "subtype": desc.get("subtype", "success"),
                "session_id": desc.get("session_id", ""),
                "duration_ms": desc.get("duration_ms", 0),
                "total_cost_usd": desc.get("total_cost_usd", 0.0),
                "num_turns": desc.get("num_turns", 0),
                "result": desc.get("result", ""),
                "is_error": desc.get("is_error", False),
            }
        )

    if kind == "user":
        return json.dumps(
            {
                "type": "user",
                "tool_use_result": desc.get("tool_use_result"),
            }
        )

    raise ValueError(f"Unknown fixture kind: {kind}")


def build_jsonl_lines(fixture_name: str) -> list[bytes]:
    """Load a fixture JSON file and return JSONL lines as bytes (with newline)."""
    fixture_path = FIXTURES_DIR / fixture_name
    with open(fixture_path) as f:
        descs = json.load(f)
    return [(_fixture_to_jsonl(d) + "\n").encode() for d in descs]


# ── Mock subprocess ───────────────────────────────────────────────────────


class MockStdout:
    """Async readline()-compatible stdout that yields pre-built JSONL lines."""

    def __init__(self, lines: list[bytes]):
        self._lines = list(lines)
        self._index = 0

    async def readline(self) -> bytes:
        if self._index < len(self._lines):
            line = self._lines[self._index]
            self._index += 1
            return line
        return b""  # EOF


class MockStderr:
    """Async readline()-compatible stderr that is always empty."""

    async def readline(self) -> bytes:
        return b""


class MockProcess:
    """Mock of asyncio.subprocess.Process for testing."""

    def __init__(self, stdout_lines: list[bytes]):
        self.stdout = MockStdout(stdout_lines)
        self.stderr = MockStderr()
        self.returncode = 0
        self.pid = 99999

    async def wait(self):
        return 0

    def terminate(self):
        pass


def make_mock_subprocess(fixture_name: str):
    """Return an async function that creates a MockProcess from a fixture file."""
    lines = build_jsonl_lines(fixture_name)

    async def _mock_create_subprocess_exec(*args, **kwargs):
        return MockProcess(lines)

    return _mock_create_subprocess_exec


# ── WebSocket helpers ───────────────────────────────────────────────────────


def collect_ws_messages(ws, until_type: str, max_msgs: int = 50) -> list[dict]:
    """Read WebSocket messages until a message of `until_type` is seen or limit reached."""
    received = []
    for _ in range(max_msgs):
        try:
            data = ws.receive_json(mode="text")
            received.append(data)
            if data.get("type") == until_type:
                break
        except Exception:
            break
    return received


# ── Server fixture ──────────────────────────────────────────────────────────


@pytest.fixture
def patched_server(tmp_path):
    """Import server.py with DB isolated to tmp_path.

    Yields the server module with:
    - DB_PATH pointing to tmp_path/bosun.db
    - app.state.workdir set to tmp_path
    - Caller patches asyncio.create_subprocess_exec for the mock subprocess
    """
    db_path = tmp_path / "bosun.db"

    # Create test-local DB
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(db_path))
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("""
        CREATE TABLE IF NOT EXISTS artifacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            msg_id TEXT NOT NULL,
            slot TEXT NOT NULL DEFAULT '1',
            type TEXT NOT NULL,
            label TEXT,
            data TEXT,
            mime_type TEXT,
            meta TEXT,
            created_at REAL DEFAULT (unixepoch('subsec')),
            UNIQUE(session_id, msg_id, slot)
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            msg_id TEXT NOT NULL,
            text TEXT NOT NULL,
            created_at REAL DEFAULT (unixepoch('subsec')),
            UNIQUE(session_id, msg_id)
        )
    """)
    db.commit()
    db.close()

    with patch.object(server, "DB_PATH", db_path):
        server.app.state.workdir = str(tmp_path)
        yield server
