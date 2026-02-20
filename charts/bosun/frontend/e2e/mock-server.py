#!/usr/bin/env python3
"""
Mock server for Playwright e2e tests.

Patches server.query with a mock that yields a deterministic fixture sequence,
then serves the Bosun frontend on port 8420.
"""

import asyncio
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock

# Add backend to path so we can import the server module
backend_dir = Path(__file__).resolve().parent.parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

# -- Mock the claude_agent_sdk before importing server -----------------------

mock_sdk = types.ModuleType("claude_agent_sdk")
mock_sdk_types = types.ModuleType("claude_agent_sdk.types")


class SystemMessage:
    def __init__(self, **kwargs):
        self.type = "system"
        self.__dict__.update(kwargs)


class ResultMessage:
    def __init__(self, **kwargs):
        self.type = "result"
        self.__dict__.update(kwargs)


class StreamEvent:
    def __init__(self, **kwargs):
        self.type = "stream_event"
        self.__dict__.update(kwargs)

    class ContentBlockStart:
        def __init__(self, content_block=None):
            self.type = "content_block_start"
            self.content_block = content_block

    class ContentBlockDelta:
        def __init__(self, delta=None):
            self.type = "content_block_delta"
            self.delta = delta

    class MessageStop:
        def __init__(self):
            self.type = "message_stop"


class TextBlock:
    def __init__(self, text=""):
        self.type = "text"
        self.text = text


class ToolUseBlock:
    def __init__(self, **kwargs):
        self.type = "tool_use"
        self.__dict__.update(kwargs)


class ToolResultBlock:
    def __init__(self, **kwargs):
        self.type = "tool_result"
        self.__dict__.update(kwargs)


class AssistantMessage:
    def __init__(self, **kwargs):
        self.type = "assistant"
        self.__dict__.update(kwargs)


class UserMessage:
    def __init__(self, **kwargs):
        self.type = "user"
        self.__dict__.update(kwargs)


class ClaudeAgentOptions:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


# Install mock SDK types
mock_sdk.query = None  # will be patched below
mock_sdk.ClaudeAgentOptions = ClaudeAgentOptions
mock_sdk.SystemMessage = SystemMessage
mock_sdk.AssistantMessage = AssistantMessage
mock_sdk.UserMessage = UserMessage
mock_sdk.ResultMessage = ResultMessage
mock_sdk.TextBlock = TextBlock
mock_sdk.ToolUseBlock = ToolUseBlock
mock_sdk.ToolResultBlock = ToolResultBlock
mock_sdk_types.StreamEvent = StreamEvent

sys.modules["claude_agent_sdk"] = mock_sdk
sys.modules["claude_agent_sdk.types"] = mock_sdk_types

# Also mock google genai so server doesn't need it
mock_google = types.ModuleType("google")
mock_genai = types.ModuleType("google.genai")
mock_genai_types = types.ModuleType("google.genai.types")
mock_google.genai = mock_genai
mock_genai.types = mock_genai_types
sys.modules["google"] = mock_google
sys.modules["google.genai"] = mock_genai
sys.modules["google.genai.types"] = mock_genai_types


# -- Mock query function ----------------------------------------------------


async def mock_query(**kwargs):
    """Yield a deterministic fixture: init -> text stream -> message_stop -> result."""

    # 1. SystemMessage (init)
    yield SystemMessage(message="session_init")

    # 2. StreamEvent: text content "Hello from mock"
    yield StreamEvent(
        event=StreamEvent.ContentBlockStart(content_block=TextBlock(text=""))
    )
    yield StreamEvent(
        event=StreamEvent.ContentBlockDelta(
            delta=types.SimpleNamespace(type="text_delta", text="Hello from mock")
        )
    )
    yield StreamEvent(event=StreamEvent.MessageStop())

    # 3. ResultMessage
    yield ResultMessage(
        text="Hello from mock",
        session_id=kwargs.get("options", ClaudeAgentOptions()).session_id
        if hasattr(kwargs.get("options", ClaudeAgentOptions()), "session_id")
        else "mock-session-id",
    )


mock_sdk.query = mock_query

# -- Import and configure the server ----------------------------------------

import server  # noqa: E402

server.HAS_SDK = True
server.HAS_GEMINI = False
server.query = mock_query
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
