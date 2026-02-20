#!/usr/bin/env python3
"""
Bosun — FastAPI backend bridging the web UI to Claude Code via Agent SDK.

Uses the Claude Agent SDK (`claude-agent-sdk`) for typed async streaming,
session management, and tool handling. Forwards events to the browser over WebSocket.

Usage:
    pip install fastapi "uvicorn[standard]" claude-agent-sdk
    python server.py [--port 8420] [--workdir /path/to/project]

Or with Vite dev server (for hot reload):
    npm run dev    # runs both backend + Vite frontend
"""

import argparse
import asyncio
import base64
import json
import logging
import os
import re
import sqlite3
import subprocess
import struct
import sys
import time
from pathlib import Path

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.responses import FileResponse, Response, StreamingResponse
    from fastapi.staticfiles import StaticFiles
    import uvicorn
except ImportError:
    sys.exit("Install dependencies: pip install fastapi 'uvicorn[standard]'")

try:
    from claude_agent_sdk import (
        query,
        ClaudeAgentOptions,
        SystemMessage,
        AssistantMessage,
        UserMessage,
        ResultMessage,
        TextBlock,
        ToolUseBlock,
        ToolResultBlock,
    )
    from claude_agent_sdk.types import StreamEvent

    HAS_SDK = True
except ImportError:
    HAS_SDK = False

# Optional Gemini TTS
try:
    from google import genai
    from google.genai import types

    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bosun")

# ── Config ──────────────────────────────────────────────────────────────────

# Unset CLAUDECODE to allow nested Claude sessions via the SDK.
# When this server runs inside a Claude Code session, the CLI sets CLAUDECODE
# which prevents launching child sessions. Clearing it here is safe because
# the server is an independent process that intentionally spawns Claude sessions.
os.environ.pop("CLAUDECODE", None)

# Resolve the system Claude CLI path (not the SDK's bundled version, which lacks auth).
# Check common locations since npm/sh may not have the full PATH from fish/zsh.
CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "")
if not CLAUDE_BIN:
    for candidate in ["/opt/homebrew/bin/claude", "/usr/local/bin/claude"]:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            CLAUDE_BIN = candidate
            break
if not CLAUDE_BIN:
    import shutil

    CLAUDE_BIN = shutil.which("claude") or ""
CLAUDE_CLI_PATH = CLAUDE_BIN or None
if CLAUDE_CLI_PATH:
    log.info("Using system Claude CLI: %s", CLAUDE_CLI_PATH)
else:
    log.warning("System claude not found — SDK will use bundled CLI (may lack auth)")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
if not GOOGLE_API_KEY:
    # Try fish shell universal variables as fallback
    try:
        GOOGLE_API_KEY = subprocess.check_output(
            ["fish", "-c", "echo $GOOGLE_API_KEY"], text=True
        ).strip()
        if GOOGLE_API_KEY:
            log.info("Loaded GOOGLE_API_KEY from fish shell")
    except Exception:
        pass

# Tools that are auto-approved (no user prompt needed)
AUTO_APPROVED_TOOLS = [
    "Read",
    "Glob",
    "Grep",
    "WebSearch",
    "WebFetch",
    "Bash",
    "Edit",
    "Write",
    "Task",
    "TaskCreate",
    "TaskUpdate",
    "TaskList",
    "SendMessage",
    "Teammate",  # Enable swarm/team tools
]

app = FastAPI()


@app.get("/health")
async def health():
    return {"status": "ok"}


# ── SQLite persistence ─────────────────────────────────────────────────────

DB_PATH = Path.home() / ".claude" / "bosun.db"


def _init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(DB_PATH))
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
    db.execute("CREATE INDEX IF NOT EXISTS idx_art_session ON artifacts(session_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_sum_session ON summaries(session_id)")
    db.commit()
    db.close()


_init_db()


def _get_db():
    """Get a SQLite connection (lightweight with WAL mode)."""
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    return db


def _save_artifact(session_id: str, msg_id: str, slot: str, artifact: dict):
    """Upsert an artifact row."""
    db = _get_db()
    try:
        db.execute(
            """INSERT INTO artifacts (session_id, msg_id, slot, type, label, data, mime_type, meta)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(session_id, msg_id, slot) DO UPDATE SET
                 type=excluded.type, label=excluded.label, data=excluded.data,
                 mime_type=excluded.mime_type, meta=excluded.meta""",
            (
                session_id,
                msg_id,
                slot,
                artifact.get("type", ""),
                artifact.get("label", ""),
                artifact.get("data", ""),
                artifact.get("mimeType", ""),
                json.dumps(artifact.get("meta")) if artifact.get("meta") else None,
            ),
        )
        db.commit()
    except Exception as e:
        log.warning("Failed to save artifact: %s", e)
    finally:
        db.close()


def _save_summary(session_id: str, msg_id: str, text: str):
    """Upsert a summary row."""
    db = _get_db()
    try:
        db.execute(
            """INSERT INTO summaries (session_id, msg_id, text)
               VALUES (?, ?, ?)
               ON CONFLICT(session_id, msg_id) DO UPDATE SET text=excluded.text""",
            (session_id, msg_id, text),
        )
        db.commit()
    except Exception as e:
        log.warning("Failed to save summary: %s", e)
    finally:
        db.close()


if not HAS_SDK:
    log.warning("claude-agent-sdk not installed — run: pip install claude-agent-sdk")

# ── Claude Agent SDK session manager ────────────────────────────────────────


class ClaudeSession:
    """Manages a Claude Agent SDK session and streams results to a WebSocket."""

    def __init__(self, workdir: str):
        self.workdir = workdir
        self.session_id: str | None = None
        self._cancel_event = asyncio.Event()

    async def run(self, prompt: str, ws: WebSocket):
        """Run a query via the Agent SDK and stream events to the WebSocket."""
        self._cancel_event.clear()

        options = ClaudeAgentOptions(
            cwd=self.workdir,
            allowed_tools=AUTO_APPROVED_TOOLS,
            permission_mode="acceptEdits",
            include_partial_messages=True,
            setting_sources=["project"],
            cli_path=CLAUDE_CLI_PATH or None,
            stderr=lambda line: log.info("claude stderr: %s", line.rstrip()),
        )
        if self.session_id:
            options.resume = self.session_id

        log.info("SDK query: %s... (session=%s)", prompt[:60], self.session_id or "new")

        text_buf = ""
        full_run_text = ""
        streaming_text = False
        artifact_counter = 0  # Counter for generating unique msg_ids for artifacts

        got_result = False

        try:
            msg_iter = query(prompt=prompt, options=options).__aiter__()
            while True:
                try:
                    msg = await msg_iter.__anext__()
                except StopAsyncIteration:
                    log.info("SDK iteration ended (StopAsyncIteration)")
                    break
                except Exception as iter_err:
                    if "Unknown message type" in str(iter_err):
                        log.warning("SDK: skipping unknown message type: %s", iter_err)
                        continue
                    raise

                log.debug("SDK msg: %s", type(msg).__name__)

                # Check for cancellation
                if self._cancel_event.is_set():
                    log.info("Query cancelled by user")
                    break

                # ── System messages (session init, etc.) ──────────
                if isinstance(msg, SystemMessage):
                    if msg.subtype == "init":
                        self.session_id = msg.data.get("session_id")
                        await ws.send_json(
                            {
                                "type": "session_init",
                                "session_id": self.session_id,
                            }
                        )
                    continue

                # ── Streaming deltas (partial text from API) ──────
                if isinstance(msg, StreamEvent):
                    ev = msg.event
                    ev_type = ev.get("type", "")

                    if ev_type == "content_block_start":
                        cb = ev.get("content_block", {})
                        if cb.get("type") == "text" and not streaming_text:
                            await ws.send_json({"type": "assistant_start"})
                            streaming_text = True
                            text_buf = ""
                        elif cb.get("type") == "tool_use":
                            await ws.send_json(
                                {
                                    "type": "tool_use",
                                    "name": cb.get("name", ""),
                                    "tool_use_id": cb.get("id", ""),
                                    "summary": f"Using {cb.get('name', '')}",
                                    "parent_tool_use_id": msg.parent_tool_use_id,
                                }
                            )

                    elif ev_type == "content_block_delta":
                        delta = ev.get("delta", {})
                        if delta.get("type") == "text_delta":
                            chunk = delta.get("text", "")
                            text_buf += chunk
                            await ws.send_json(
                                {
                                    "type": "assistant_text",
                                    "content": chunk,
                                }
                            )

                    elif ev_type == "message_stop":
                        if streaming_text:
                            full_run_text += text_buf + "\n"
                            await ws.send_json(
                                {
                                    "type": "assistant_done",
                                    "full_text": text_buf,
                                }
                            )
                            # Scan for mermaid blocks in the completed text
                            for mi, mblock in enumerate(
                                _extract_mermaid_blocks(text_buf)
                            ):
                                await ws.send_json(
                                    {
                                        "type": "mermaid_artifact",
                                        "code": mblock["code"],
                                        "label": mblock["label"],
                                    }
                                )
                                # Auto-save mermaid artifact
                                if self.session_id:
                                    artifact_counter += 1
                                    _save_artifact(
                                        self.session_id,
                                        f"mermaid-{artifact_counter}",
                                        str(mi + 1),
                                        {
                                            "type": "mermaid",
                                            "label": mblock["label"],
                                            "data": mblock["code"],
                                        },
                                    )
                            streaming_text = False
                            text_buf = ""

                    continue

                # ── Complete assistant messages ────────────────────
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, ToolUseBlock):
                            await ws.send_json(
                                {
                                    "type": "tool_use",
                                    "name": block.name,
                                    "tool_use_id": block.id,
                                    "input": block.input,
                                    "summary": _tool_summary_sdk(block),
                                    "parent_tool_use_id": msg.parent_tool_use_id,
                                }
                            )
                        elif isinstance(block, TextBlock) and block.text:
                            full_run_text += block.text + "\n"
                        elif isinstance(block, ToolResultBlock):
                            content = block.content
                            images = (
                                _extract_images(content)
                                if isinstance(content, list)
                                else []
                            )
                            if isinstance(content, list):
                                content = "\n".join(
                                    b.get("text", "")
                                    for b in content
                                    if isinstance(b, dict) and b.get("type") == "text"
                                )
                            result_msg = {
                                "type": "tool_result",
                                "tool_use_id": block.tool_use_id,
                                "name": getattr(block, "name", None) or "",
                                "output": str(content or "")[:5000],
                            }
                            if getattr(block, "is_error", False):
                                result_msg["is_error"] = True
                            if images:
                                result_msg["image"] = images[0]
                                # Auto-save image artifact
                                if self.session_id:
                                    artifact_counter += 1
                                    _save_artifact(
                                        self.session_id,
                                        f"tool-{artifact_counter}",
                                        "1",
                                        {
                                            "type": "image",
                                            "label": block.name or "screenshot",
                                            "data": images[0].get("data", ""),
                                            "mimeType": images[0].get(
                                                "mimeType", "image/png"
                                            ),
                                        },
                                    )
                            await ws.send_json(result_msg)
                    continue

                # ── User messages (tool results flowing back) ─────
                if isinstance(msg, UserMessage):
                    if msg.tool_use_result:
                        tur = msg.tool_use_result
                        # MCP tool results may be a list of content blocks
                        # instead of a dict with "content" key
                        if isinstance(tur, list):
                            content = tur
                            tool_use_id = ""
                        elif isinstance(tur, dict):
                            content = tur.get("content", "")
                            tool_use_id = tur.get("tool_use_id", "")
                        else:
                            content = str(tur)
                            tool_use_id = ""
                        images = (
                            _extract_images(content)
                            if isinstance(content, list)
                            else []
                        )
                        if isinstance(content, list):
                            content = "\n".join(
                                b.get("text", "")
                                for b in content
                                if isinstance(b, dict) and b.get("type") == "text"
                            )
                        result_msg = {
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "output": str(content or "")[:5000],
                        }
                        if images:
                            result_msg["image"] = images[0]
                            # Auto-save image artifact
                            if self.session_id:
                                artifact_counter += 1
                                _save_artifact(
                                    self.session_id,
                                    f"user-tool-{artifact_counter}",
                                    "1",
                                    {
                                        "type": "image",
                                        "label": "screenshot",
                                        "data": images[0].get("data", ""),
                                        "mimeType": images[0].get(
                                            "mimeType", "image/png"
                                        ),
                                    },
                                )
                        await ws.send_json(result_msg)
                    continue

                # ── Final result ──────────────────────────────────
                if isinstance(msg, ResultMessage):
                    self.session_id = msg.session_id

                    # Send any remaining streaming text
                    if streaming_text:
                        full_run_text += text_buf + "\n"
                        await ws.send_json(
                            {
                                "type": "assistant_done",
                                "full_text": text_buf,
                            }
                        )
                        streaming_text = False

                    final_text = full_run_text.strip() or (msg.result or "")
                    log.info(
                        "SDK result: session=%s, turns=%s, text_len=%d",
                        msg.session_id,
                        msg.num_turns,
                        len(final_text),
                    )
                    got_result = True
                    await ws.send_json(
                        {
                            "type": "result",
                            "session_id": msg.session_id,
                            "cost_usd": msg.total_cost_usd,
                            "duration_ms": msg.duration_ms,
                            "num_turns": msg.num_turns,
                            "full_text": final_text,
                        }
                    )
                    continue

        except asyncio.CancelledError:
            log.info("SDK query task cancelled")
            raise
        except Exception as e:
            log.error("SDK query error: %s", e)
            try:
                await ws.send_json({"type": "error", "message": str(e)})
            except Exception:
                pass

        # Fallback: if SDK iteration ended without a ResultMessage, send
        # accumulated text so the frontend can still trigger TTS/summary.
        if not got_result and full_run_text.strip():
            log.warning(
                "SDK ended without ResultMessage — sending fallback result (text_len=%d)",
                len(full_run_text.strip()),
            )
            if streaming_text:
                full_run_text += text_buf + "\n"
                await ws.send_json(
                    {"type": "assistant_done", "full_text": text_buf}
                )
            await ws.send_json(
                {
                    "type": "result",
                    "session_id": self.session_id,
                    "full_text": full_run_text.strip(),
                }
            )

    def cancel(self):
        """Signal the running query to stop."""
        self._cancel_event.set()


def _tool_summary_sdk(block: ToolUseBlock) -> str:
    """Generate a human-readable summary for a SDK ToolUseBlock."""
    name = block.name
    inp = block.input

    if name == "Edit":
        return f"Edit: {inp.get('file_path', 'file')}"
    if name == "Write":
        return f"Write: {inp.get('file_path', 'file')}"
    if name == "Read":
        return f"Read: {inp.get('file_path', 'file')}"
    if name == "Bash":
        cmd = inp.get("command", "")
        return f"Run: {cmd[:80]}"
    if name == "Glob":
        return f"Search: {inp.get('pattern', '')}"
    if name == "Grep":
        return f"Grep: {inp.get('pattern', '')}"
    if name == "TaskCreate":
        return f"Task: {inp.get('subject', '')}"
    if name == "TaskUpdate":
        return f"TaskUpdate: #{inp.get('taskId', '')} → {inp.get('status', '')}"
    if name == "Task":
        return f"Agent: {inp.get('name', inp.get('description', ''))}"
    if name == "SendMessage":
        return f"Message → {inp.get('recipient', inp.get('type', ''))}"

    return name


# Keep old helper for session history parsing (uses dicts, not SDK types)
def _tool_summary(block: dict) -> str:
    """Generate a human-readable summary for a tool use dict (JSONL parsing)."""
    name = block.get("name", "")
    inp = block.get("input", {})

    if name == "Edit":
        return f"Edit: {inp.get('file_path', 'file')}"
    if name == "Write":
        return f"Write: {inp.get('file_path', 'file')}"
    if name == "Read":
        return f"Read: {inp.get('file_path', 'file')}"
    if name == "Bash":
        cmd = inp.get("command", "")
        return f"Run: {cmd[:80]}"
    if name == "Glob":
        return f"Search: {inp.get('pattern', '')}"
    if name == "Grep":
        return f"Grep: {inp.get('pattern', '')}"

    return name


_MERMAID_RE = re.compile(r"```mermaid\s*\n(.*?)\n```", re.DOTALL)


def _extract_mermaid_blocks(text: str) -> list[dict]:
    """Extract mermaid code blocks from markdown text."""
    blocks = []
    for i, m in enumerate(_MERMAID_RE.finditer(text)):
        code = m.group(1).strip()
        if code:
            blocks.append({"code": code, "label": f"diagram-{i + 1}"})
    return blocks


def _extract_images(content) -> list[dict]:
    """Extract image data from SDK content blocks."""
    images = []
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "image":
                source = block.get("source", {})
                if source.get("type") == "base64":
                    images.append(
                        {
                            "data": source.get("data", ""),
                            "mimeType": source.get("media_type", "image/png"),
                        }
                    )
    return images


# ── Session history endpoint ─────────────────────────────────────────────────


def _sessions_dir_for_workdir(workdir: str) -> Path:
    """Derive the Claude Code sessions directory for a given workdir.

    Claude Code stores sessions at ~/.claude/projects/<encoded-path>/*.jsonl
    where <encoded-path> is the workdir with / replaced by -.
    """
    encoded = workdir.replace("/", "-")
    return Path.home() / ".claude" / "projects" / encoded


def _parse_session_preview(filepath: Path, max_lines: int = 50) -> dict | None:
    """Parse a session JSONL file to extract metadata for listing."""
    sid = filepath.stem
    stat = filepath.stat()
    mtime = stat.st_mtime
    size_kb = stat.st_size // 1024

    preview = ""
    cwd = ""
    msg_count = 0

    try:
        with open(filepath) as f:
            for i, line in enumerate(f):
                if i > max_lines:
                    break
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                otype = obj.get("type", "")
                if otype == "user":
                    msg_count += 1
                    if not cwd:
                        cwd = obj.get("cwd", "")
                    if not preview:
                        content = obj.get("message", {}).get("content", "")
                        if isinstance(content, str):
                            # Strip system-reminder tags
                            text = content
                            if "<" in text:
                                import re

                                text = re.sub(
                                    r"<[^>]+>.*?</[^>]+>", "", text, flags=re.DOTALL
                                ).strip()
                            preview = text[:120]
                        elif isinstance(content, list):
                            for c in content:
                                if isinstance(c, dict) and c.get("type") == "text":
                                    text = c["text"]
                                    if "<" in text:
                                        import re

                                        text = re.sub(
                                            r"<[^>]+>.*?</[^>]+>",
                                            "",
                                            text,
                                            flags=re.DOTALL,
                                        ).strip()
                                    preview = text[:120]
                                    break
                elif otype == "assistant":
                    msg_count += 1
    except Exception as e:
        log.warning("Failed to parse session %s: %s", sid, e)
        return None

    if not preview:
        return None  # Skip empty sessions

    return {
        "id": sid,
        "preview": preview,
        "cwd": cwd,
        "mtime": mtime,
        "size_kb": size_kb,
        "msg_count": msg_count,
    }


def _all_projects_dirs() -> list[Path]:
    """Return all Claude Code project directories."""
    base = Path.home() / ".claude" / "projects"
    if not base.exists():
        return []
    return [d for d in base.iterdir() if d.is_dir()]


def _find_session_file(session_id: str) -> Path | None:
    """Search all project directories for a session JSONL file."""
    for proj_dir in _all_projects_dirs():
        candidate = proj_dir / f"{session_id}.jsonl"
        if candidate.exists():
            return candidate
    return None


@app.get("/api/sessions")
async def list_sessions(limit: int = 50, all_projects: bool = True):
    """List recent Claude Code sessions.

    By default scans all projects. Pass all_projects=false to only show
    sessions for the configured workdir.
    """
    if all_projects:
        dirs = _all_projects_dirs()
    else:
        workdir = app.state.workdir
        sessions_dir = _sessions_dir_for_workdir(workdir)
        dirs = [sessions_dir] if sessions_dir.exists() else []

    # Collect all JSONL files across project dirs, sorted by mtime
    all_files = []
    for d in dirs:
        project_name = d.name  # e.g. "-Users-jomcgi-repos-homelab"
        for f in d.glob("*.jsonl"):
            all_files.append((f, project_name))

    all_files.sort(key=lambda x: x[0].stat().st_mtime, reverse=True)
    all_files = all_files[:limit]

    sessions = []
    for f, project_name in all_files:
        info = _parse_session_preview(f)
        if info:
            # Decode project name back to path for display
            readable_project = (
                project_name.replace("-", "/", 1)
                if project_name.startswith("-")
                else project_name
            )
            info["project"] = readable_project
            sessions.append(info)

    return {"sessions": sessions}


@app.get("/api/sessions/{session_id}/messages")
async def get_session_messages(session_id: str, limit: int = 200):
    """Load conversation messages from a session JSONL file."""
    import re as _re

    filepath = _find_session_file(session_id)
    if not filepath:
        return {"messages": [], "error": "Session not found"}

    messages = []
    try:
        with open(filepath) as f:
            for line in f:
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                otype = obj.get("type", "")

                if otype == "user":
                    content = obj.get("message", {}).get("content", "")
                    text = ""
                    if isinstance(content, str):
                        text = content
                    elif isinstance(content, list):
                        for c in content:
                            if isinstance(c, dict) and c.get("type") == "text":
                                text = c["text"]
                                break

                    # Strip system-reminder tags
                    if "<" in text:
                        text = _re.sub(
                            r"<[^>]+>.*?</[^>]+>", "", text, flags=_re.DOTALL
                        ).strip()

                    if text:
                        messages.append(
                            {
                                "role": "voice",
                                "text": text[:2000],
                            }
                        )

                elif otype == "assistant":
                    msg = obj.get("message", {})
                    for block in msg.get("content", []):
                        if (
                            block.get("type") == "text"
                            and block.get("text", "").strip()
                        ):
                            messages.append(
                                {
                                    "role": "claude",
                                    "status": "done",
                                    "text": block["text"][:2000],
                                }
                            )
                        elif block.get("type") == "tool_use":
                            messages.append(
                                {
                                    "role": "claude",
                                    "status": "tool",
                                    "text": _tool_summary(block),
                                }
                            )

                if len(messages) >= limit:
                    break

    except Exception as e:
        log.error("Failed to load session %s: %s", session_id, e)
        return {"messages": [], "error": str(e)}

    return {"messages": messages, "session_id": session_id}


# ── Artifact + Summary persistence API ────────────────────────────────────────


@app.post("/api/artifacts")
async def save_artifact(body: dict):
    """Upsert an artifact for a session message."""
    session_id = body.get("session_id")
    msg_id = body.get("msg_id")
    slot = body.get("slot", "1")
    artifact = body.get("artifact", {})
    if not session_id or not msg_id or not artifact:
        return {"error": "Missing session_id, msg_id, or artifact"}
    _save_artifact(session_id, msg_id, slot, artifact)
    return {"ok": True}


@app.get("/api/sessions/{session_id}/artifacts")
async def get_session_artifacts(session_id: str):
    """Return all artifacts for a session, ordered by created_at."""
    db = _get_db()
    try:
        rows = db.execute(
            "SELECT * FROM artifacts WHERE session_id = ? ORDER BY created_at",
            (session_id,),
        ).fetchall()
        artifacts = []
        for r in rows:
            artifacts.append(
                {
                    "id": r["id"],
                    "session_id": r["session_id"],
                    "msg_id": r["msg_id"],
                    "slot": r["slot"],
                    "type": r["type"],
                    "label": r["label"],
                    "data": r["data"],
                    "mimeType": r["mime_type"],
                    "meta": json.loads(r["meta"]) if r["meta"] else None,
                    "created_at": r["created_at"],
                }
            )
        return {"artifacts": artifacts}
    finally:
        db.close()


@app.post("/api/summaries")
async def save_summary_endpoint(body: dict):
    """Upsert a TTS summary for a session message."""
    session_id = body.get("session_id")
    msg_id = body.get("msg_id")
    text = body.get("text", "")
    if not session_id or not msg_id or not text:
        return {"error": "Missing session_id, msg_id, or text"}
    _save_summary(session_id, msg_id, text)
    return {"ok": True}


@app.get("/api/sessions/{session_id}/summaries")
async def get_session_summaries(session_id: str):
    """Return all summaries for a session, ordered by created_at."""
    db = _get_db()
    try:
        rows = db.execute(
            "SELECT * FROM summaries WHERE session_id = ? ORDER BY created_at",
            (session_id,),
        ).fetchall()
        summaries = []
        for r in rows:
            summaries.append(
                {
                    "id": r["id"],
                    "session_id": r["session_id"],
                    "msg_id": r["msg_id"],
                    "text": r["text"],
                    "created_at": r["created_at"],
                }
            )
        return {"summaries": summaries}
    finally:
        db.close()


# ── Gemini TTS + title generation ────────────────────────────────────────────

_gemini_client = None


def _get_gemini():
    global _gemini_client
    if _gemini_client is None:
        if not HAS_GEMINI:
            return None
        key = GOOGLE_API_KEY
        if not key:
            return None
        _gemini_client = genai.Client(api_key=key)
    return _gemini_client


def _pcm_to_wav(
    pcm_data: bytes, sample_rate: int = 24000, channels: int = 1, bits: int = 16
) -> bytes:
    """Wrap raw PCM audio bytes in a WAV header."""
    data_size = len(pcm_data)
    byte_rate = sample_rate * channels * bits // 8
    block_align = channels * bits // 8

    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,  # file size - 8
        b"WAVE",
        b"fmt ",
        16,  # fmt chunk size
        1,  # PCM format
        channels,
        sample_rate,
        byte_rate,
        block_align,
        bits,
        b"data",
        data_size,
    )
    return header + pcm_data


# ── TTS helpers and caching ────────────────────────────────────────────────

_TTS_CACHE: dict[str, str] = {}  # phrase -> base64 WAV audio
_TTS_CACHE_PATH = Path.home() / ".claude" / "tts_cache.json"

_CACHED_PHRASES = [
    "Compacting session context",
    "Starting new session",
    "Cancelled",
    "Muted",
    "Unmuted",
    "Approved",
    "Rejected",
    "Nothing to approve",
    "Nothing to reject",
    "Nothing to repeat",
    "Claude is currently working",
    "Claude is idle",
    "No recent sessions",
    "Could not load sessions",
    "Could not search sessions",
    "No matching session found",
]


def _generate_tts_raw(text: str) -> bytes | None:
    """Generate raw PCM audio from Google Cloud TTS Chirp3-HD (synchronous, for thread pool)."""
    import urllib.request

    if not GOOGLE_API_KEY:
        return None
    url = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={GOOGLE_API_KEY}"
    payload = json.dumps(
        {
            "input": {"text": text},
            "voice": {"languageCode": "en-US", "name": "en-US-Chirp3-HD-Kore"},
            "audioConfig": {"audioEncoding": "LINEAR16", "sampleRateHertz": 24000},
        }
    ).encode()
    try:
        req = urllib.request.Request(
            url, data=payload, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
        return base64.b64decode(data["audioContent"])
    except Exception as e:
        log.warning("TTS generation failed: %s", e)
        return None


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences at . ! ? boundaries."""
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p for p in parts if p.strip()]


async def _precache_tts():
    """Pre-generate TTS audio for static confirmation phrases.

    Loads previously cached audio from disk (PVC-backed) and only generates
    missing phrases, so pod restarts don't re-hit the TTS API.
    """
    # Load existing cache from PVC
    if _TTS_CACHE_PATH.exists():
        try:
            saved = json.loads(_TTS_CACHE_PATH.read_text())
            _TTS_CACHE.update(saved)
            log.info("TTS cache: loaded %d phrases from disk", len(saved))
        except Exception as e:
            log.warning("TTS cache: failed to load from disk: %s", e)

    missing = [p for p in _CACHED_PHRASES if p not in _TTS_CACHE]
    if not missing:
        log.info(
            "TTS cache: all %d phrases already cached on disk", len(_CACHED_PHRASES)
        )
        return

    if not GOOGLE_API_KEY:
        log.info(
            "TTS cache: GOOGLE_API_KEY not set, skipping %d missing phrases",
            len(missing),
        )
        return

    log.info("TTS cache: generating %d missing phrases...", len(missing))
    for phrase in missing:
        try:
            pcm = await asyncio.to_thread(_generate_tts_raw, phrase)
            if pcm:
                wav = _pcm_to_wav(pcm, sample_rate=24000)
                _TTS_CACHE[phrase] = base64.b64encode(wav).decode("utf-8")
        except Exception as e:
            log.warning("TTS cache: failed '%s': %s", phrase, e)

    # Persist to PVC so next restart skips generation
    try:
        _TTS_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _TTS_CACHE_PATH.write_text(json.dumps(_TTS_CACHE))
        log.info("TTS cache: saved %d phrases to disk", len(_TTS_CACHE))
    except Exception as e:
        log.warning("TTS cache: failed to save to disk: %s", e)

    log.info("TTS cache: cached %d/%d phrases", len(_TTS_CACHE), len(_CACHED_PHRASES))


@app.on_event("startup")
async def _startup():
    asyncio.create_task(_precache_tts())


@app.get("/api/tts/cache")
async def get_tts_cache():
    """Return all pre-cached TTS audio for client-side instant playback."""
    return {"cache": _TTS_CACHE, "mime_type": "audio/wav"}


@app.post("/api/intent")
async def classify_intent(body: dict):
    """Classify voice input as a command or message using Gemini Flash."""
    client = _get_gemini()
    if not client:
        return {"intent": "message"}  # Fallback: treat as message

    text = body.get("text", "")
    if not text:
        return {"intent": "message"}

    context = body.get("context", {})

    prompt = (
        "You classify short voice commands for a coding assistant UI.\n"
        "The user is either giving a UI command OR a task/question for the coding agent.\n"
        "If the input sounds like a task, question, or instruction for a coding agent, "
        "reply 'message'. When in doubt, prefer 'message'.\n\n"
        f"Context: streaming={context.get('streaming')}, "
        f"approval_pending={context.get('has_pending_approval')}\n\n"
        "Available commands (ONLY match if clearly intended):\n"
        "- new_session: user wants to start a fresh conversation (e.g. 'new session', 'start over')\n"
        "- cancel: user wants to stop the current task (e.g. 'cancel', 'stop', 'nevermind')\n"
        "- repeat: user wants to hear the last response again (e.g. 'say that again', 'repeat')\n"
        "- list_sessions: user asks what sessions exist (e.g. 'list my sessions')\n"
        "- switch_session: user wants to switch to a different session (e.g. 'go back to the auth one')\n"
        "- status: user asks if the UI/agent is busy or idle (e.g. 'what's happening', 'are you busy')\n"
        "- mute/unmute: user wants to toggle spoken responses\n"
        "- approve/reject: user responds to a pending tool approval\n"
        "- compact: user wants to compress/summarize the session context\n"
        "- message: anything else -- tasks, questions, instructions for the coding agent\n\n"
        f'Voice input: "{text}"\n\n'
        "Reply with ONLY the command name. "
        "If switch_session, add |query. Example: switch_session|the auth fix\n"
        "If compact, add |directive. Example: compact|summarize the auth changes"
    )

    try:
        response = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-3-flash-preview",
            contents=prompt,
        )
        raw = response.text.strip().lower()
        if "|" in raw:
            intent, param = raw.split("|", 1)
            return {"intent": intent.strip(), "params": {"query": param.strip()}}
        return {"intent": raw if raw != "message" else "message"}
    except Exception as e:
        log.warning("Intent classification failed: %s", e)
        return {"intent": "message"}


@app.post("/api/sessions/search")
async def search_sessions(body: dict):
    """Fuzzy search sessions by natural language query using Gemini."""
    client = _get_gemini()
    search_query = body.get("query", "")
    if not client or not search_query:
        return {"matches": []}

    # Load recent session previews
    dirs = _all_projects_dirs()
    all_files = []
    for d in dirs:
        for f in d.glob("*.jsonl"):
            all_files.append(f)
    all_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    all_files = all_files[:30]

    previews = []
    for f in all_files:
        info = _parse_session_preview(f)
        if info:
            previews.append(info)

    if not previews:
        return {"matches": []}

    # Ask Gemini to match
    listing = "\n".join(
        f"{i}. [{p['id'][:8]}] {p['preview'][:80]}" for i, p in enumerate(previews)
    )
    prompt = (
        f"Given these coding sessions:\n{listing}\n\n"
        f'Which session best matches the query: "{search_query}"?\n'
        "Reply with ONLY the index number (0-based). If no good match, reply -1."
    )

    try:
        response = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-3-flash-preview",
            contents=prompt,
        )
        idx = int(response.text.strip())
        if 0 <= idx < len(previews):
            return {"matches": [previews[idx]]}
        return {"matches": []}
    except Exception:
        return {"matches": []}


@app.get("/api/status")
async def get_status():
    """Return current session status for voice readback."""
    ws_endpoint = getattr(app.state, "_ws_status", {})
    return {
        "session_id": ws_endpoint.get("session_id"),
        "streaming": ws_endpoint.get("streaming", False),
        "queue_depth": ws_endpoint.get("queue_depth", 0),
        "connected": ws_endpoint.get("connected", False),
    }


def _truncate_for_tts(text: str) -> str:
    """Keep first ~500 chars + last ~1500 chars, breaking at sentence boundaries."""
    if len(text) <= 2000:
        return text
    head = text[:500]
    tail = text[-1500:]
    head_break = head.rfind(".")
    if head_break > 200:
        head = head[: head_break + 1]
    tail_break = tail.find(".")
    if 0 < tail_break < 200:
        tail = tail[tail_break + 1 :].lstrip()
    return head + "\n[...]\n" + tail


_SUMMARY_PROMPT = (
    "You are briefing a developer who is listening, not reading. Summarize this\n"
    "coding agent's output as a spoken paragraph (100-150 words, 3-5 sentences).\n\n"
    "Structure:\n"
    "1. What was found or done (1-2 sentences)\n"
    "2. The recommendation or proposed next step (1-2 sentences)\n"
    "3. Any question the agent is asking the user (if applicable)\n\n"
    "Rules:\n"
    '- Lead with the conclusion/finding, not "The agent investigated..."\n'
    "- Include specific details (file names, function names, values) so the\n"
    "  listener can respond with instructions without seeing the screen\n"
    "- If the agent asks the user a question, end with that question\n"
    "- Be natural and conversational — this will be spoken aloud\n"
    "- Do NOT use markdown, bullet points, or formatting\n\n"
)


async def _summarize(client, text: str, suggest_actions: bool):
    """Summarize agent output for spoken delivery. Returns (spoken_text, summary, actions)."""
    try:
        if suggest_actions:
            sa_prompt = (
                _SUMMARY_PROMPT
                + "Then suggest 1-3 follow-up actions the user might want.\n\n"
                "Output format (JSON only, no markdown):\n"
                '{"summary": "...", "actions": [{"label": "Run tests", "prompt": "run the test suite"}]}\n\n'
                f"Agent output:\n{text}"
            )
            sa_resp = await asyncio.to_thread(
                client.models.generate_content,
                model="gemini-3-flash-preview",
                contents=sa_prompt,
            )
            raw = sa_resp.text.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
                if raw.endswith("```"):
                    raw = raw[:-3]
                raw = raw.strip()
            parsed = json.loads(raw)
            summary = parsed.get("summary", "").strip().strip('"').strip("'")
            actions = parsed.get("actions", [])
            return summary, summary, actions
        else:
            resp = await asyncio.to_thread(
                client.models.generate_content,
                model="gemini-3-flash-preview",
                contents=_SUMMARY_PROMPT + f"Agent output:\n{text}",
            )
            summary = resp.text.strip().strip('"').strip("'")
            return summary, summary, []
    except Exception as e:
        log.warning("Summary failed, speaking full text: %s", e)
        return text, None, []


async def _stream_tts(client, text: str, summarize: bool, suggest_actions: bool):
    """Stream TTS as NDJSON: first sentence audio arrives ASAP, then the rest."""
    text = _truncate_for_tts(text)

    # Step 1: Summarize
    if summarize or suggest_actions:
        spoken_text, summary_text, actions = await _summarize(
            client, text, suggest_actions
        )
        log.info("Stream TTS summary: %s", spoken_text[:120])
    else:
        spoken_text, summary_text, actions = text, None, []

    # Step 2: Split into sentences for pipelining
    sentences = _split_sentences(spoken_text)

    if len(sentences) <= 1:
        # Short — single TTS call
        pcm = await asyncio.to_thread(_generate_tts_raw, spoken_text)
        if pcm:
            wav = _pcm_to_wav(pcm, sample_rate=24000)
            yield (
                json.dumps(
                    {"audio": base64.b64encode(wav).decode(), "mime_type": "audio/wav"}
                )
                + "\n"
            )
    else:
        # Pipeline: first sentence + rest run concurrently
        first_sentence = sentences[0]
        rest = " ".join(sentences[1:])

        first_task = asyncio.create_task(
            asyncio.to_thread(_generate_tts_raw, first_sentence)
        )
        rest_task = asyncio.create_task(asyncio.to_thread(_generate_tts_raw, rest))

        # Yield first sentence audio ASAP
        first_pcm = await first_task
        if first_pcm:
            wav = _pcm_to_wav(first_pcm, sample_rate=24000)
            yield (
                json.dumps(
                    {"audio": base64.b64encode(wav).decode(), "mime_type": "audio/wav"}
                )
                + "\n"
            )

        # Yield remaining audio
        rest_pcm = await rest_task
        if rest_pcm:
            wav = _pcm_to_wav(rest_pcm, sample_rate=24000)
            yield (
                json.dumps(
                    {"audio": base64.b64encode(wav).decode(), "mime_type": "audio/wav"}
                )
                + "\n"
            )

    # Final metadata
    result = {"done": True}
    if summary_text:
        result["summary"] = summary_text
    if actions:
        result["actions"] = actions
    yield json.dumps(result) + "\n"


@app.post("/api/tts")
async def text_to_speech(body: dict):
    """Generate speech audio from text using Google Cloud TTS (Chirp3-HD).

    Supports streaming (stream=true) for pipelined TTS: first sentence audio
    arrives while remaining sentences are still being generated.
    Summarization (if requested) uses Gemini Flash.
    """
    if not GOOGLE_API_KEY:
        return {"error": "GOOGLE_API_KEY not configured"}

    client = _get_gemini()  # needed for summarization only

    text = body.get("text", "")
    if not text:
        return {"error": "No text provided"}

    # Check pre-cache for exact matches (static confirmations)
    if text in _TTS_CACHE:
        return {"audio": _TTS_CACHE[text], "mime_type": "audio/wav"}

    summarize = body.get("summarize", False)
    suggest_actions = body.get("suggest_actions", False)

    # Streaming mode: NDJSON with pipelined audio chunks
    if body.get("stream"):
        return StreamingResponse(
            _stream_tts(client, text, summarize, suggest_actions),
            media_type="application/x-ndjson",
        )

    # Non-streaming (legacy) path
    text = _truncate_for_tts(text)

    if summarize or suggest_actions:
        spoken_text, summary_text, actions = await _summarize(
            client, text, suggest_actions
        )
        log.info("TTS summary: %s", spoken_text[:120])
    else:
        spoken_text, summary_text, actions = text, None, []

    try:
        pcm = await asyncio.to_thread(_generate_tts_raw, spoken_text)
        if not pcm:
            return {"error": "TTS generation failed"}
        wav_audio = _pcm_to_wav(pcm, sample_rate=24000)
        audio_b64 = base64.b64encode(wav_audio).decode("utf-8")
        result = {"audio": audio_b64, "mime_type": "audio/wav"}
        if summary_text:
            result["summary"] = summary_text
        if actions:
            result["actions"] = actions
        return result

    except Exception as e:
        log.error("Cloud TTS error: %s", e)
        return {"error": str(e)}


@app.post("/api/title")
async def generate_title(body: dict):
    """Generate a short session title from conversation messages using Gemini."""
    client = _get_gemini()
    if not client:
        return {"error": "Gemini not configured"}

    messages = body.get("messages", [])
    if not messages:
        return {"error": "No messages provided"}

    # Build a condensed transcript
    transcript = ""
    for m in messages[:10]:  # First 10 messages max
        role = "User" if m.get("role") == "voice" else "Claude"
        text = m.get("text", "")[:200]
        transcript += f"{role}: {text}\n"

    try:
        response = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-3-flash-preview",
            contents=f"Generate a short title (3-6 words, no quotes) summarizing this coding session:\n\n{transcript}",
        )
        title = response.text.strip().strip('"').strip("'")
        return {"title": title}

    except Exception as e:
        log.error("Gemini title error: %s", e)
        return {"error": str(e)}


# ── WebSocket endpoint ──────────────────────────────────────────────────────


async def _compact_session(session_id: str | None, directive: str = "") -> str:
    """Summarize a session's conversation via Gemini for context compaction."""
    client = _get_gemini()
    if not client or not session_id:
        return ""

    filepath = _find_session_file(session_id)
    if not filepath:
        return ""

    # Load last N messages from session JSONL
    messages_text = []
    try:
        with open(filepath) as f:
            for line in f:
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                otype = obj.get("type", "")
                if otype == "user":
                    content = obj.get("message", {}).get("content", "")
                    if isinstance(content, str) and content.strip():
                        messages_text.append(f"User: {content[:200]}")
                elif otype == "assistant":
                    for block in obj.get("message", {}).get("content", []):
                        if (
                            block.get("type") == "text"
                            and block.get("text", "").strip()
                        ):
                            messages_text.append(f"Assistant: {block['text'][:200]}")
    except Exception as e:
        log.warning("Failed to read session for compaction: %s", e)
        return ""

    # Take last 30 messages to stay within Gemini context
    recent = messages_text[-30:]
    transcript = "\n".join(recent)

    focus = f" Focus on: {directive}" if directive else ""
    prompt = (
        f"Summarize this coding session concisely.{focus}\n"
        "Include: what was worked on, key decisions made, current state, and any pending tasks.\n"
        "Keep it under 300 words.\n\n"
        f"{transcript}"
    )

    try:
        response = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-2.5-flash",
            contents=prompt,
        )
        return response.text.strip()
    except Exception as e:
        log.warning("Session compaction failed: %s", e)
        return ""


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    log.info("WebSocket connected")

    workdir = app.state.workdir
    session = ClaudeSession(workdir)
    current_task: asyncio.Task | None = None
    message_queue: list[str] = []  # Queued messages for when agent is busy

    # Expose status for the /api/status endpoint
    def _update_status():
        app.state._ws_status = {
            "session_id": session.session_id,
            "streaming": current_task is not None and not current_task.done(),
            "queue_depth": len(message_queue),
            "connected": True,
        }

    _update_status()

    async def drain_queue():
        """Process queued messages sequentially after the current turn finishes."""
        while message_queue:
            next_text = message_queue.pop(0)
            _update_status()
            log.info(
                "Draining queued message (%d remaining): %s...",
                len(message_queue),
                next_text[:60],
            )
            await ws.send_json(
                {
                    "type": "queue_drain",
                    "text": next_text,
                    "remaining": len(message_queue),
                }
            )
            await session.run(next_text, ws)

    async def run_and_drain(text: str):
        """Run a prompt then drain any queued follow-ups."""
        _update_status()
        await session.run(text, ws)
        _update_status()
        await drain_queue()

    try:
        while True:
            data = await ws.receive_json()
            msg_type = data.get("type")

            if msg_type == "message":
                text = data.get("text", "").strip()
                if not text:
                    continue

                if current_task and not current_task.done():
                    # Agent is busy — queue the message for delivery after current turn
                    message_queue.append(text)
                    _update_status()
                    log.info(
                        "Queued message (%d in queue): %s...",
                        len(message_queue),
                        text[:60],
                    )
                    await ws.send_json(
                        {
                            "type": "queued",
                            "text": text,
                            "position": len(message_queue),
                        }
                    )
                else:
                    # Agent is idle — run immediately
                    current_task = asyncio.create_task(run_and_drain(text))
                    _update_status()

            elif msg_type == "clear_queue":
                # Clear queued messages without cancelling current task
                cleared = len(message_queue)
                message_queue.clear()
                _update_status()
                if cleared:
                    log.info("Cleared %d queued message(s)", cleared)

            elif msg_type == "cancel":
                # Explicit cancel — signal query to stop, clear queue
                message_queue.clear()
                if current_task and not current_task.done():
                    session.cancel()
                    current_task.cancel()
                    try:
                        await current_task
                    except asyncio.CancelledError:
                        pass
                _update_status()
                await ws.send_json({"type": "cancelled"})
                log.info("Cancelled current task and cleared queue")

            elif msg_type == "resume":
                sid = data.get("session_id")
                if sid:
                    session.session_id = sid
                    _update_status()
                    log.info("Resuming session: %s", sid)

            elif msg_type == "new_session":
                # Cancel any running task and clear queue
                message_queue.clear()
                if current_task and not current_task.done():
                    session.cancel()
                    current_task.cancel()
                    try:
                        await current_task
                    except asyncio.CancelledError:
                        pass
                session = ClaudeSession(workdir)
                _update_status()
                log.info("New session created")

            elif msg_type == "compact":
                # Compact current session: summarize via Gemini, start fresh
                directive = data.get("message", "")
                log.info(
                    "Compacting session (directive: %s)",
                    directive[:60] if directive else "none",
                )

                # Cancel current task if running
                message_queue.clear()
                if current_task and not current_task.done():
                    session.cancel()
                    current_task.cancel()
                    try:
                        await current_task
                    except asyncio.CancelledError:
                        pass

                # Build summary of current conversation
                old_sid = session.session_id
                summary = await _compact_session(old_sid, directive)

                # Create fresh session seeded with the summary
                session = ClaudeSession(workdir)
                _update_status()

                if summary:
                    seed_prompt = f"[Context from previous session]\n{summary}\n\n[Continue from here]"
                    current_task = asyncio.create_task(run_and_drain(seed_prompt))
                    _update_status()
                    await ws.send_json({"type": "compacted", "old_session_id": old_sid})
                else:
                    await ws.send_json(
                        {
                            "type": "compacted",
                            "old_session_id": old_sid,
                            "warning": "No summary generated",
                        }
                    )

            elif msg_type == "status":
                # Return current status over WS for voice readback
                await ws.send_json(
                    {
                        "type": "status_response",
                        "session_id": session.session_id,
                        "streaming": current_task is not None
                        and not current_task.done(),
                        "queue_depth": len(message_queue),
                    }
                )

    except WebSocketDisconnect:
        log.info("WebSocket disconnected")
    except Exception as e:
        log.error("WebSocket error: %s", e)
    finally:
        message_queue.clear()
        app.state._ws_status = {"connected": False}
        if current_task and not current_task.done():
            session.cancel()
            current_task.cancel()


# ── Static file serving (production mode) ───────────────────────────────────

STATIC_DIR = Path(__file__).parent / "dist"

if STATIC_DIR.exists():

    @app.get("/")
    async def serve_index():
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/", StaticFiles(directory=STATIC_DIR), name="static")


# ── CLI entry point ─────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Bosun backend server")
    parser.add_argument(
        "--port", type=int, default=8420, help="Server port (default: 8420)"
    )
    parser.add_argument(
        "--workdir",
        type=str,
        default=os.getcwd(),
        help="Working directory for Claude Code",
    )
    parser.add_argument(
        "--host", type=str, default="127.0.0.1", help="Bind host (default: 127.0.0.1)"
    )
    args = parser.parse_args()

    app.state.workdir = os.path.abspath(args.workdir)
    log.info("Working directory: %s", app.state.workdir)
    log.info("Starting server at http://%s:%d", args.host, args.port)

    if not STATIC_DIR.exists():
        log.info(
            "No dist/ found — run 'npm run build' or use Vite dev server for frontend"
        )
        log.info("  Vite dev: cd tools/bosun && npm run dev")
        log.info("  Vite proxies /ws to this backend automatically")

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
