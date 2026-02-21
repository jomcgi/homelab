#!/usr/bin/env python3
"""
Mock server for Playwright e2e tests.

Patches asyncio.create_subprocess_exec with a mock that yields a deterministic
JSONL fixture sequence, then serves the Bosun frontend on port 8420.
"""

import asyncio
import json
import sys
import types
from pathlib import Path
from unittest.mock import patch

# Add backend to path so we can import the server module
backend_dir = Path(__file__).resolve().parent.parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

# Mock google genai so server doesn't need it
mock_google = types.ModuleType("google")
mock_genai = types.ModuleType("google.genai")
mock_genai_types = types.ModuleType("google.genai.types")
mock_google.genai = mock_genai
mock_genai.types = mock_genai_types
sys.modules["google"] = mock_google
sys.modules["google.genai"] = mock_genai
sys.modules["google.genai.types"] = mock_genai_types


# -- Mock subprocess --------------------------------------------------------


class MockStdout:
    def __init__(self):
        self._lines = [
            json.dumps(
                {"type": "system", "subtype": "init", "session_id": "mock-session-id"}
            )
            + "\n",
            json.dumps(
                {
                    "type": "stream_event",
                    "event": {
                        "type": "content_block_start",
                        "content_block": {"type": "text"},
                    },
                }
            )
            + "\n",
            json.dumps(
                {
                    "type": "stream_event",
                    "event": {
                        "type": "content_block_delta",
                        "delta": {"type": "text_delta", "text": "Hello from mock"},
                    },
                }
            )
            + "\n",
            json.dumps({"type": "stream_event", "event": {"type": "message_stop"}})
            + "\n",
            json.dumps(
                {
                    "type": "result",
                    "subtype": "success",
                    "session_id": "mock-session-id",
                    "duration_ms": 100,
                    "total_cost_usd": 0.001,
                    "num_turns": 1,
                    "result": "Hello from mock",
                    "is_error": False,
                }
            )
            + "\n",
        ]
        self._index = 0

    async def readline(self):
        if self._index < len(self._lines):
            line = self._lines[self._index].encode()
            self._index += 1
            return line
        return b""


class MockStderr:
    async def readline(self):
        return b""


class MockProcess:
    def __init__(self):
        self.stdout = MockStdout()
        self.stderr = MockStderr()
        self.returncode = 0
        self.pid = 99999

    async def wait(self):
        return 0

    def terminate(self):
        pass


async def mock_create_subprocess(*args, **kwargs):
    return MockProcess()


# -- Import and configure the server ----------------------------------------

# Patch create_subprocess_exec before importing server so the first call works
_orig_create = asyncio.create_subprocess_exec
asyncio.create_subprocess_exec = mock_create_subprocess

import server  # noqa: E402

server.HAS_GEMINI = False
server.app.state.workdir = "/tmp"

# Serve static files from dist/ if it exists
dist_dir = Path(__file__).resolve().parent.parent / "dist"
if dist_dir.is_dir():
    from fastapi.staticfiles import StaticFiles

    server.app.mount(
        "/", StaticFiles(directory=str(dist_dir), html=True), name="static"
    )

# -- Run ---------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(server.app, host="0.0.0.0", port=8420, log_level="info")
