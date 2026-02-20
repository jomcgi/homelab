"""
Shared fixtures and helpers for Bosun integration tests.

Converts fixture JSON files into SDK types, mocks `server.query`,
and provides WebSocket message collection utilities.

This is a pytest conftest — fixtures are auto-discovered by tests
in this directory without explicit imports.
"""

import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

import charts.bosun.backend.server as server
from claude_agent_sdk import (
    SystemMessage,
    AssistantMessage,
    UserMessage,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    ToolResultBlock,
)
from claude_agent_sdk.types import StreamEvent

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ── SDK event builders ──────────────────────────────────────────────────────


def _build_sdk_event(desc: dict):
    """Convert a fixture JSON dict into the corresponding SDK type."""
    kind = desc["kind"]

    if kind == "system_init":
        return SystemMessage(subtype="init", data=desc["data"])

    if kind == "stream_event":
        return StreamEvent(
            uuid=desc["uuid"],
            session_id=desc["session_id"],
            event=desc["event"],
            parent_tool_use_id=desc.get("parent_tool_use_id"),
        )

    if kind == "assistant":
        blocks = []
        for block_desc in desc["content"]:
            btype = block_desc["type"]
            if btype == "text":
                blocks.append(TextBlock(text=block_desc["text"]))
            elif btype == "tool_use":
                blocks.append(
                    ToolUseBlock(
                        id=block_desc["id"],
                        name=block_desc["name"],
                        input=block_desc.get("input", {}),
                    )
                )
            elif btype == "tool_result":
                blocks.append(
                    ToolResultBlock(
                        tool_use_id=block_desc["tool_use_id"],
                        content=block_desc.get("content", ""),
                        is_error=block_desc.get("is_error", False),
                    )
                )
        return AssistantMessage(
            content=blocks,
            model=desc.get("model", "claude-sonnet-4-5-20250929"),
            parent_tool_use_id=desc.get("parent_tool_use_id"),
        )

    if kind == "result":
        return ResultMessage(
            subtype=desc.get("subtype", "success"),
            session_id=desc["session_id"],
            duration_ms=desc.get("duration_ms", 0),
            duration_api_ms=desc.get("duration_api_ms", 0),
            total_cost_usd=desc.get("total_cost_usd", 0.0),
            num_turns=desc.get("num_turns", 0),
            result=desc.get("result", ""),
            is_error=desc.get("is_error", False),
            usage=desc.get("usage", {}),
            structured_output=None,
        )

    if kind == "user":
        return UserMessage(
            tool_use_result=desc.get("tool_use_result"),
        )

    raise ValueError(f"Unknown fixture kind: {kind}")


def build_sdk_events(fixture_name: str) -> list:
    """Load a fixture JSON file and return a list of SDK event objects."""
    fixture_path = FIXTURES_DIR / fixture_name
    with open(fixture_path) as f:
        descs = json.load(f)
    return [_build_sdk_event(d) for d in descs]


def make_mock_query(events: list):
    """Return an async generator function that yields the given SDK events."""

    async def _mock_query(**kwargs):
        for event in events:
            yield event

    return _mock_query


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
    - Caller patches server.query via: patch.object(server, "query", ...)
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
